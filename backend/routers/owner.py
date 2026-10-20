"""GET /api/v1/owner/* — the owner API (docs/v2/SPEC.md §2, §3).

S1.1 adds the settings endpoints; S1.4 adds home / area / report / ask beside them. Owner-only: the owner
(staff_role OWNER) and ADMIN/SUPERADMIN pass `require_staff_role`; every other staff role gets a 403. The
restaurant is always resolved from the caller's own tenant (routers/deps.py) — there is no restaurant_id
parameter anywhere in this API, so there is no id to forge.

Observer-mode deployments (read-only Macsoft) block this whole prefix, like /overview, /reports and /ai
(observer_mode.py): these endpoints compose figures from local tables.
"""
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, create_model
from sqlalchemy.orm import Session

import models
from auth import require_staff_role
from database import get_db
from owner import areas as owner_areas
from owner import ask as owner_ask
from owner import home as owner_home
from owner import preview as owner_preview
from owner import reports as owner_reports
from owner import settings as owner_settings
from owner.money.ledger import parse_month
from owner.states import OwnerContext
from routers.deps import get_restaurant_or_none
from time_utils import utcnow

router = APIRouter(prefix="/owner", tags=["owner"])

_owner_only = require_staff_role(models.StaffRole.OWNER)


def _restaurant(db: Session, user: models.User) -> models.Restaurant:
    restaurant = get_restaurant_or_none(db, user)
    if restaurant is None:
        raise HTTPException(404, "Restaurant not found")
    return restaurant


# The PATCH body is generated from the same FieldSpec list the service validates against, so the allowed
# range exists once (owner/settings.py) and FastAPI reports an out-of-range value as a 422 on that field.
SettingsPatch = create_model(
    "SettingsPatch",
    __config__=ConfigDict(extra="forbid"),
    **{
        spec.key: (
            Optional[StrictInt if spec.kind == "int" else StrictFloat],
            Field(None, ge=spec.minimum, le=spec.maximum, description=spec.question),
        )
        for spec in owner_settings.FIELDS
    },
)


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """Every setting with its value, default, allowed range and the question in owner words."""
    restaurant = _restaurant(db, user)
    return owner_settings.describe(db, restaurant.id)


@router.put("/settings")
def write_settings(body: SettingsPatch, db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """Change one or more settings (send only the ones that change). Out-of-range → 422; each change is audited."""
    restaurant = _restaurant(db, user)
    changes = body.model_dump(exclude_none=True)
    try:
        owner_settings.update_settings(db, restaurant.id, user.id, changes)
    except owner_settings.SettingsError as exc:
        raise HTTPException(422, detail={"field": exc.field, "message": str(exc)}) from exc
    return owner_settings.describe(db, restaurant.id)


@router.post("/settings/preview")
def preview_settings(body: SettingsPatch, db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """What a change would do to Home's cards, worked out with the real engines and rolled back: nothing is saved or audited."""
    restaurant = _restaurant(db, user)
    try:
        return owner_preview.preview_settings(db, user, restaurant, body.model_dump(exclude_none=True))
    except owner_settings.SettingsError as exc:
        raise HTTPException(422, detail={"field": exc.field, "message": str(exc)}) from exc


@router.get("/settings/history")
def settings_history(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
                     user: models.User = Depends(_owner_only)):
    restaurant = _restaurant(db, user)
    return {"history": owner_settings.history(db, restaurant.id, limit)}


def _context(db: Session, user: models.User) -> OwnerContext:
    return OwnerContext(db, user, _restaurant(db, user))


@router.get("/home")
def home(period: str = Query("today", pattern="^(today|7d|30d)$"), db: Session = Depends(get_db),
         user: models.User = Depends(_owner_only)):
    """Home in one call: pulse, costing-you-money, health tiles, the six areas, coming up, LEVIII's read."""
    return owner_home.compose_home(_context(db, user), period)


@router.get("/area/{key}")
def area(key: str, db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """One area, the very block Home embeds (so Home and the deep link cannot disagree)."""
    if key not in owner_areas.AREAS:
        raise HTTPException(404, "Unknown area")
    return owner_areas.compose_area(_context(db, user), key)


@router.get("/report/{period}")
def report(period: str, month: Optional[str] = Query(None, description="monthly only: a past or current month, as 2026-09"),
           db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """daily · weekly · monthly · yearly. Sections that are not built yet say so (`planned`). `month` (monthly report only) makes
    every section cover that whole calendar month."""
    if period not in owner_reports.PERIODS:
        raise HTTPException(404, "Unknown report")
    first = None
    if month is not None:
        if period != "monthly":
            raise HTTPException(422, "A month can only be chosen for the monthly report")
        try:
            first = parse_month(month)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
    return owner_reports.compose_report(_context(db, user), period, first)


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=3, max_length=500)
    form: Optional[Literal["what", "why", "what_if", "what_to_do", "compare"]] = Field(
        None, description="The form of answer. Left out, the words of the question choose it.")
    conversation_id: Optional[int] = Field(None, ge=1, description="Save the question and its answer in this conversation (Previous conversations).")
    client_message_id: Optional[str] = Field(None, max_length=64, description="Asking again with the same id returns the saved answer instead of working it out twice.")


@router.post("/ask")
def ask(body: AskBody, db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """Ask LEVIII, in five forms: what · why · what if · what should I do · compare. Every answer is worked out by code from the
    restaurant's own records and carries its state; the language model never computes a figure. With a `conversation_id` the exchange
    is saved in the owner's own conversation history."""
    restaurant = _restaurant(db, user)
    question = body.question.strip()
    conversation = None
    if body.conversation_id is not None:
        conversation = db.query(models.OwnerOSConversation).filter_by(
            id=body.conversation_id, owner_user_id=user.id, restaurant_id=restaurant.id).with_for_update().first()
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        if body.client_message_id:
            prior = db.query(models.OwnerOSMessage).filter_by(
                conversation_id=conversation.id, role="user", client_message_id=body.client_message_id).first()
            if prior:
                saved = db.query(models.OwnerOSMessage).filter(
                    models.OwnerOSMessage.conversation_id == conversation.id, models.OwnerOSMessage.role == "assistant",
                    models.OwnerOSMessage.id > prior.id).order_by(models.OwnerOSMessage.id.asc()).first()
                if saved:
                    return {**json.loads(saved.content), "conversation_id": conversation.id}
    answer = owner_ask.ask(OwnerContext(db, user, restaurant), question, body.form)
    if conversation is not None:
        db.add(models.OwnerOSMessage(conversation_id=conversation.id, role="user", content=question, client_message_id=body.client_message_id))
        db.add(models.OwnerOSMessage(conversation_id=conversation.id, role="assistant", content=json.dumps(answer, ensure_ascii=False),
                                     answer_type=f"owner_{answer['form']}"))
        conversation.updated_at = utcnow()
        db.commit()
        answer = {**answer, "conversation_id": conversation.id}
    return answer
