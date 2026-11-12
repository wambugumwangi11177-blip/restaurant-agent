"""Step gate for the storekeeper: account, recipes, then questions (next run)."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

import auth
import models
from ai.notify import notify_users
from database import get_db
from routers.auth import LOCKOUT_MINUTES, MAX_FAILED_ATTEMPTS
from routers.deps import get_or_create_restaurant
from schemas import StrictModel
from staff_audit import record_entry
from time_utils import utcnow

router = APIRouter(prefix="/staff-setup", tags=["staff-setup"])

_QUESTIONS = Path(__file__).resolve().parents[2] / "config" / "storekeeper-questions.json"


class AccountStep(StrictModel):
    current_password: str
    new_password: str
    pin: str = Field(min_length=4, max_length=4)


def load_questions() -> dict:
    raw = json.loads(_QUESTIONS.read_text(encoding="utf-8"))
    questions = []
    for item in raw.get("questions", []):
        questions.append({
            "id": item["id"],
            "prompt": item["prompt"],
            "answers": [
                {
                    "value": answer["value"],
                    "opens": answer.get("opens"),
                    "unlocks": answer.get("unlocks"),
                }
                for answer in item.get("answers", [])
            ],
        })
    return {"version": raw.get("version", 1), "questions": questions}


def _progress(db: Session, user: models.User, restaurant_id: int) -> models.StaffSetupProgress:
    row = db.query(models.StaffSetupProgress).filter(
        models.StaffSetupProgress.user_id == user.id
    ).first()
    if row is None:
        row = models.StaffSetupProgress(
            user_id=user.id,
            restaurant_id=restaurant_id,
            updated_at=utcnow(),
        )
        db.add(row)
        db.flush()
    return row


def _step_state(progress: models.StaffSetupProgress | None, user: models.User) -> dict:
    account_done = bool(user.hashed_pin) and not user.must_change_password and (
        progress is None or progress.account_completed_at is not None or not user.must_change_password
    )
    # A storekeeper created through this flow has a progress row. Account is
    # done only when that timestamp is set. Legacy staff with no row and no
    # forced change are not stuck on step 1.
    if progress is not None:
        account_done = progress.account_completed_at is not None
    elif user.must_change_password or not user.hashed_pin:
        account_done = False
    recipes_done = bool(progress and progress.recipes_completed_at)
    questions = load_questions()
    if account_done and recipes_done:
        question_state = "locked"
        question_reason = (
            "Each answer opens a page or unlocks a module. The questions are saved. "
            "Answering them is the next release."
        )
    elif account_done:
        question_state = "locked"
        question_reason = "Save at least one recipe from the chefs. That unlocks this step's questions."
    else:
        question_state = "locked"
        question_reason = "Change the password you were given and set your own 4-digit PIN first."
    return {
        "must_change_password": bool(user.must_change_password),
        "has_pin": bool(user.hashed_pin),
        "app_unlocked": bool(account_done and recipes_done),
        "steps": [
            {
                "id": "account",
                "title": "Your login",
                "state": "done" if account_done else "open",
                "unlocks": "Recipe entry, then the rest of the store",
                "locked_reason": None if account_done else "Sign in, replace the temporary password, and choose a 4-digit PIN.",
                "completed_at": progress.account_completed_at.isoformat() if progress and progress.account_completed_at else None,
            },
            {
                "id": "recipes",
                "title": "Recipes from the chefs",
                "state": "done" if recipes_done else ("open" if account_done else "locked"),
                "unlocks": "Stock counts and the question step",
                "locked_reason": None if (account_done or recipes_done) else "Unlocks after your password and PIN are saved.",
                "completed_at": progress.recipes_completed_at.isoformat() if progress and progress.recipes_completed_at else None,
            },
            {
                "id": "questionnaire",
                "title": "A few questions",
                "state": question_state,
                "unlocks": "A specific page or module for each answer",
                "locked_reason": question_reason,
                "completed_at": None,
                "runnable": False,
                "questions": questions["questions"],
            },
        ],
    }


def _notify_owners(db: Session, user: models.User, restaurant: models.Restaurant, title: str, body: str) -> None:
    owners = db.query(models.User).filter(
        models.User.tenant_id == user.tenant_id,
        models.User.role.in_((models.Role.ADMIN, models.Role.SUPERADMIN)),
        models.User.is_active.is_(True),
        models.User.id != user.id,
    ).all()
    if not owners:
        return
    notify_users(
        db,
        [owner.id for owner in owners],
        title,
        body,
        "staff.setup",
        url="/eleven/staff",
    )


@router.get("")
async def get_setup(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    progress = db.query(models.StaffSetupProgress).filter(
        models.StaffSetupProgress.user_id == current_user.id
    ).first()
    # Don't create a row just by looking. Creation happens when the owner
    # makes the login, or when this person finishes a step.
    payload = _step_state(progress, current_user)
    payload["restaurant_id"] = restaurant.id
    return payload


@router.post("/account")
async def complete_account(
    body: AccountStep,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if user.pin_locked_until and user.pin_locked_until > utcnow():
        remaining = int((user.pin_locked_until - utcnow()).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Account temporarily locked due to repeated failed PIN attempts. Try again in {remaining} minute(s).",
        )
    if user.locked_until and user.locked_until > utcnow():
        remaining = int((user.locked_until - utcnow()).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Account temporarily locked. Try again in {remaining} minute(s).",
        )
    if not auth.verify_password(body.current_password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            from datetime import timedelta
            user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect password")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="Choose a password that is different from the temporary one.")
    auth.require_strong_password(body.new_password)
    if not body.pin.isdigit() or len(body.pin) != 4:
        raise HTTPException(status_code=400, detail="PIN must be 4 digits.")
    restaurant = get_or_create_restaurant(db, user)
    user.hashed_password = auth.get_password_hash(body.new_password)
    user.hashed_pin = auth.get_pin_hash(body.pin)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    progress = _progress(db, user, restaurant.id)
    progress.account_completed_at = utcnow()
    progress.updated_at = utcnow()
    record_entry(
        db, restaurant.id, user, "account_ready", "user",
        f"{user.email} set their own password and 4-digit PIN.",
        entity_id=user.id,
        detail={"pin_length": 4},
    )
    db.commit()
    _notify_owners(
        db, user, restaurant,
        "Store setup: login saved",
        f"{user.email} changed the temporary password and set a PIN.",
    )
    return _step_state(progress, user)


@router.post("/recipes")
async def complete_recipes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if user.staff_role not in (
        models.StaffRole.STOCKKEEPER,
        models.StaffRole.KITCHEN,
        models.StaffRole.MANAGER,
    ) and user.role not in (models.Role.ADMIN, models.Role.SUPERADMIN):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this action")
    restaurant = get_or_create_restaurant(db, user)
    progress = db.query(models.StaffSetupProgress).filter(
        models.StaffSetupProgress.user_id == user.id
    ).first()
    if user.role not in (models.Role.ADMIN, models.Role.SUPERADMIN):
        if progress is None or progress.account_completed_at is None:
            raise HTTPException(status_code=403, detail="password_change_required")
    line_count = (
        db.query(models.MenuIngredient)
        .join(models.MenuItem, models.MenuItem.id == models.MenuIngredient.menu_item_id)
        .filter(models.MenuItem.restaurant_id == restaurant.id)
        .count()
    )
    if line_count < 1:
        raise HTTPException(status_code=400, detail="Save at least one recipe line before finishing this step.")
    if progress is None:
        progress = _progress(db, user, restaurant.id)
    if progress.recipes_completed_at is None:
        progress.recipes_completed_at = utcnow()
        progress.updated_at = utcnow()
        record_entry(
            db, restaurant.id, user, "recipes_ready", "menu_ingredient",
            f"{user.email} marked {line_count} recipe line(s) as taken in from the chefs.",
            detail={"line_count": line_count},
        )
        db.commit()
        _notify_owners(
            db, user, restaurant,
            "Store setup: recipes saved",
            f"{user.email} finished taking in recipes ({line_count} line(s)).",
        )
    return _step_state(progress, user)


@router.get("/activity")
async def setup_activity(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.StaffSetupProgress, models.User)
        .join(models.User, models.User.id == models.StaffSetupProgress.user_id)
        .filter(models.StaffSetupProgress.restaurant_id == restaurant.id)
        .order_by(models.StaffSetupProgress.id.asc())
        .all()
    )
    people = []
    for progress, person in rows:
        state = _step_state(progress, person)
        people.append({
            "user_id": person.id,
            "email": person.email,
            "staff_role": person.staff_role.value if person.staff_role else None,
            "account": state["steps"][0]["state"],
            "recipes": state["steps"][1]["state"],
            "questionnaire": state["steps"][2]["state"],
            "app_unlocked": state["app_unlocked"],
            "account_completed_at": state["steps"][0]["completed_at"],
            "recipes_completed_at": state["steps"][1]["completed_at"],
        })
    audits = (
        db.query(models.StaffEntryAudit)
        .filter(models.StaffEntryAudit.restaurant_id == restaurant.id)
        .order_by(models.StaffEntryAudit.id.desc())
        .limit(40)
        .all()
    )
    names = {}
    if audits:
        users = db.query(models.User).filter(
            models.User.id.in_({row.user_id for row in audits})
        ).all()
        names = {item.id: item.email for item in users}
    return {
        "people": people,
        "entries": [
            {
                "id": row.id,
                "at": row.created_at.isoformat() if row.created_at else None,
                "email": names.get(row.user_id),
                "action": row.action,
                "summary": row.summary,
            }
            for row in audits
        ],
    }
