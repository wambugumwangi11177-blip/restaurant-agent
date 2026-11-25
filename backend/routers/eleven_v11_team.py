"""Owner Team hub (v11) — shift, PIN handovers, Jack setup answers."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from people import person_of
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.labor_schedule import nairobi_today, team_overview
from store_access import latest_answers
from routers.staff_setup import _step_state, load_questions

router = APIRouter(prefix="/eleven/team", tags=["eleven-team-v11"])


@router.get("/hub")
def team_hub(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    overview = team_overview(db, restaurant.id, nairobi_today())
    roster = (
        db.query(models.StaffMember)
        .filter(models.StaffMember.restaurant_id == restaurant.id, models.StaffMember.is_active.is_(True))
        .order_by(models.StaffMember.name)
        .all()
    )
    jack_row = (
        db.query(models.User)
        .filter(
            models.User.active_restaurant_id == restaurant.id,
            models.User.staff_role == models.StaffRole.STOCKKEEPER,
            models.User.is_active.is_(True),
        )
        .order_by(models.User.id.asc())
        .first()
    )
    jack_block = None
    if jack_row:
        progress = (
            db.query(models.StaffSetupProgress)
            .filter(
                models.StaffSetupProgress.restaurant_id == restaurant.id,
                models.StaffSetupProgress.user_id == jack_row.id,
            )
            .first()
        )
        state = _step_state(progress, jack_row) if progress else None
        answers = latest_answers(db, jack_row.id)
        jack_block = {
            "name": person_of(db, jack_row)["person_name"],
            "email": jack_row.email,
            "on_shift": any(row["name"] == person_of(db, jack_row)["person_name"] for row in overview.get("on_shift_now", [])),
            "questionnaire": state["steps"][2]["state"] if state else "not_started",
            "answers": [
                {
                    "prompt": next((q["prompt"] for q in load_questions()["questions"] if q["id"] == a.question_id), a.question_id),
                    "label": a.label or a.value,
                }
                for a in answers.values()
            ],
            "routing_mode": restaurant.restock_routing_mode,
        }
    audits = (
        db.query(models.StaffEntryAudit)
        .filter(
            models.StaffEntryAudit.restaurant_id == restaurant.id,
            models.StaffEntryAudit.action.in_(("pin_changed", "handover_reset", "sign_in_reset")),
        )
        .order_by(models.StaffEntryAudit.id.desc())
        .limit(25)
        .all()
    )
    audit_users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_({a.user_id for a in audits} or {0})).all()}
    pin_handover = [
        {
            "at": row.created_at.isoformat() if row.created_at else None,
            "action": row.action.replace("_", " "),
            "who": person_of(db, audit_users[row.user_id])["person_name"] if row.user_id in audit_users else "",
            "summary": row.summary,
        }
        for row in audits
    ]
    return {
        "overview": overview,
        "roster": [
            {
                "id": m.id,
                "name": m.name,
                "role_title": m.role_title,
                "has_login": m.user_id is not None,
                "score_note": "Reliability from schedule adherence (coming)",
            }
            for m in roster
        ],
        "jack": jack_block,
        "pin_handover_history": pin_handover,
        "restock_routing_mode": restaurant.restock_routing_mode,
    }