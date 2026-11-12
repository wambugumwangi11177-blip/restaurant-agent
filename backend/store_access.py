"""Who may use a store module, based on the latest answer to each question."""
from fastapi import HTTPException

import models


def latest_answers(db, user_id: int) -> dict[str, models.StaffSetupAnswer]:
    rows = (
        db.query(models.StaffSetupAnswer)
        .filter(models.StaffSetupAnswer.user_id == user_id)
        .order_by(models.StaffSetupAnswer.id.asc())
        .all()
    )
    return {row.question_id: row for row in rows}


def unlocked_modules(db, user: models.User) -> set[str]:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return {"*"}
    found = set()
    for row in latest_answers(db, user.id).values():
        if row.unlocks:
            found.add(row.unlocks)
    return found


def require_store_role(user: models.User) -> None:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return
    if user.staff_role != models.StaffRole.STOCKKEEPER:
        raise HTTPException(status_code=403, detail="Insufficient permissions for this action")


def require_module(db, user: models.User, module: str) -> None:
    require_store_role(user)
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return
    if module not in unlocked_modules(db, user):
        raise HTTPException(
            status_code=403,
            detail="Answer the questions first. This part is still locked.",
        )


def stock_followup(answers: dict) -> dict | None:
    """What the POS question means for the store count. None until it is answered."""
    row = answers.get("stock_in_pos")
    if row is None:
        return None
    if row.value == "yes":
        return {
            "status": "waiting_on_pos",
            "label": "Stock is waiting on the POS webhook. No opening count yet.",
            "pending": None,
        }
    if row.value == "no":
        pending = "Enter the current store stock once the real data and the till webhook are live."
        return {"status": "count_when_live", "label": pending, "pending": pending}
    return {
        "status": "unknown",
        "label": "The storekeeper does not know if stock is kept in the POS.",
        "pending": None,
    }


def can_see_prices(user: models.User) -> bool:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return True
    return user.staff_role == models.StaffRole.CONTROLLER
