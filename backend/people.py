"""Display names for people the owner sees. The email stays secondary."""
import models


def person_of(db, user) -> dict:
    if user is None:
        return {"person_name": "Someone", "person_email": "", "initial": "?"}
    member = (
        db.query(models.StaffMember)
        .filter(models.StaffMember.user_id == user.id)
        .order_by(models.StaffMember.id.asc())
        .first()
    )
    name = (member.name or "").strip() if member else ""
    if not name:
        name = (user.email or "Someone").split("@")[0]
    email = user.email or ""
    return {"person_name": name, "person_email": email, "initial": (name[:1] or "?").upper()}
