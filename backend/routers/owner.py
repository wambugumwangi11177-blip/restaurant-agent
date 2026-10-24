"""GET /api/v1/owner/* — the owner API (docs/v2/SPEC.md §2, §3).

S1.1 adds the settings endpoints; S1.4 adds home / area / report / ask beside them. Owner-only: the owner
(staff_role OWNER) and ADMIN/SUPERADMIN pass `require_staff_role`; every other staff role gets a 403. The
restaurant is always resolved from the caller's own tenant (routers/deps.py) — there is no restaurant_id
parameter anywhere in this API, so there is no id to forge.

Observer-mode deployments (read-only Macsoft) block this whole prefix, like /overview, /reports and /ai
(observer_mode.py): these endpoints compose figures from local tables.
"""
import json
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, create_model
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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


@router.get('/planning/menu-review')
def menu_review(db: Session=Depends(get_db), user=Depends(_owner_only)):
    from owner.growth import menu_review as review
    return review(OwnerContext(db,user,_restaurant(db,user)))


@router.get('/planning/branches')
def branch_review(db: Session=Depends(get_db),user=Depends(_owner_only)):
    from owner.growth import branch_review as review
    return review(OwnerContext(db,user,_restaurant(db,user)))


@router.get('/planning/forecast')
def prep_forecast(on: date, db: Session=Depends(get_db), user=Depends(_owner_only)):
    from owner.planning import forecast_portions
    try:
        return forecast_portions(OwnerContext(db,user,_restaurant(db,user)),on)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


class PriceListIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    menu_item_id: int = Field(gt=0)
    channel: Literal['all','walk_in','app','uber_eats','glovo','bolt_food'] = 'all'
    daypart: Literal['all','breakfast','lunch','afternoon','dinner','late'] = 'all'
    price_cents: StrictInt = Field(gt=0,le=100000000)
    starts_on: date
    ends_on: date | None = None
    explanation: str = Field(min_length=5,max_length=240)


@router.get('/planning/prices')
def price_lists(db: Session=Depends(get_db), user=Depends(_owner_only)):
    rid=_restaurant(db,user).id
    return [{'id':r.id,'menu_item_id':r.menu_item_id,'channel':r.channel,'daypart':r.daypart,
             'price_kes':r.price_cents/100,'starts_on':r.starts_on.isoformat(),
             'ends_on':r.ends_on.isoformat() if r.ends_on else None,'explanation':r.explanation,'active':r.is_active}
            for r in db.query(models.ScheduledMenuPrice).filter_by(restaurant_id=rid).order_by(models.ScheduledMenuPrice.id.desc()).all()]


@router.post('/planning/prices',status_code=201)
def create_price_list(body: PriceListIn, db: Session=Depends(get_db), user=Depends(_owner_only)):
    from time_utils import eat_date
    rid=_restaurant(db,user).id
    dish=db.query(models.MenuItem).filter_by(id=body.menu_item_id,restaurant_id=rid).with_for_update().first()
    if not dish:
        raise HTTPException(404,'Dish not found')
    if body.starts_on<=eat_date(utcnow()) or body.ends_on and body.ends_on<body.starts_on:
        raise HTTPException(422,'Schedule from tomorrow or later, with an end on or after the start')
    if body.daypart!='all' and body.price_cents>dish.price:
        raise HTTPException(422,'Daypart prices are discounts, never surges')
    if not body.explanation.strip():
        raise HTTPException(422,'Explain this price to your customers')
    existing=db.query(models.ScheduledMenuPrice).filter_by(restaurant_id=rid,menu_item_id=dish.id,
        channel=body.channel,daypart=body.daypart,is_active=True).all()
    if any(r.starts_on<=(body.ends_on or date.max) and (r.ends_on or date.max)>=body.starts_on for r in existing):
        raise HTTPException(409,'An active price already covers this dish, channel and period')
    rule=models.ScheduledMenuPrice(**body.model_dump(),restaurant_id=rid,created_by=user.id)
    db.add(rule);db.commit()
    return {'id':rule.id,'message':'Scheduled. Existing orders retain their recorded prices.'}


@router.delete('/planning/prices/{rule_id}')
def stop_price_list(rule_id:int,db:Session=Depends(get_db),user=Depends(_owner_only)):
    rule=db.query(models.ScheduledMenuPrice).filter_by(id=rule_id,restaurant_id=_restaurant(db,user).id).first()
    if not rule:
        raise HTTPException(404,'Price not found')
    # Active schedules are ended on the next Nairobi day, never changed mid-service.
    from time_utils import eat_date
    today=eat_date(utcnow())
    if rule.starts_on>today:
        rule.is_active=False
    else:
        rule.ends_on=min(rule.ends_on or date.max,today)
    db.commit()
    return {'message':'Future price cancelled or current price ends tonight.'}


class PlannedDish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    menu_item_id: int = Field(gt=0)
    portions: int = Field(gt=0, le=10000)


class PrepPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dishes: list[PlannedDish] = Field(min_length=1, max_length=60)


class ComboPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    menu_item_ids: list[int] = Field(min_length=2, max_length=10)
    price_cents: int = Field(gt=0, le=100000000)


class MarketDraft(PrepPlan):
    entry_key: str = Field(min_length=8,max_length=64)
    suppliers: dict[int,int] = Field(default_factory=dict)


@router.post('/planning/market-drafts',status_code=201)
def market_drafts(body:MarketDraft,db:Session=Depends(get_db),user=Depends(_owner_only)):
    from owner.planning import prepare
    from decimal import Decimal, ROUND_HALF_UP
    rid=_restaurant(db,user).id
    key=f'market:{rid}:{user.id}:{body.entry_key}'
    payload=json.dumps(body.model_dump(exclude={'entry_key'}),sort_keys=True)
    old=db.query(models.OperationEntry).filter_by(entry_key=key).first()
    if old:
        if old.payload!=payload:
            raise HTTPException(409,'Retry key already used for another plan')
        return json.loads(old.result)
    try:
        prep=prepare(OwnerContext(db,user,_restaurant(db,user)),body.dishes)
        ids=[]
        for row in prep['items']:
            if row['buy']<=0:
                continue
            sid=body.suppliers.get(row['inventory_item_id'],row['supplier_id'])
            supplier=db.query(models.Supplier).filter_by(id=sid,restaurant_id=rid).first()
            if not supplier or row['cost_per_unit_cents']<=0:
                raise ValueError(f"{row['item']}: choose a supplier and enter the unit cost first")
            total=int((Decimal(str(row['buy']))*row['cost_per_unit_cents']).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            po=models.PurchaseOrder(restaurant_id=rid,supplier_id=sid,inventory_item_id=row['inventory_item_id'],
                quantity_ordered=row['buy'],unit=row['unit'],cost_per_unit=row['cost_per_unit_cents'],total_cost=total,
                status='PENDING',notes='Owner-reviewed prep market list; approve in Purchasing before receiving.')
            db.add(po);db.flush();ids.append(po.id)
        result={'purchase_order_ids':ids,'message':f'{len(ids)} draft lines saved. Review by supplier in Purchasing; nothing sent.'}
        db.add(models.OperationEntry(restaurant_id=rid,user_id=user.id,entry_key=key,kind='market',payload=payload,result=json.dumps(result)))
        db.commit()
        return result
    except ValueError as exc:
        db.rollback();raise HTTPException(422,str(exc)) from exc
    except IntegrityError:
        db.rollback()
        prior=db.query(models.OperationEntry).filter_by(entry_key=key).first()
        if prior and prior.payload==payload:
            return json.loads(prior.result)
        raise HTTPException(409,'Plan changed during save. Reload and review the existing drafts.')


@router.post('/planning/prep')
def prep_plan(body: PrepPlan, db: Session=Depends(get_db), user=Depends(_owner_only)):
    from owner.planning import prepare
    try:
        return prepare(OwnerContext(db, user, _restaurant(db,user)), body.dishes)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.post('/planning/combo')
def combo_plan(body: ComboPlan, db: Session=Depends(get_db), user=Depends(_owner_only)):
    from owner.planning import combo
    try:
        return combo(OwnerContext(db,user,_restaurant(db,user)), body.menu_item_ids, body.price_cents)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get('/planning/shifts')
def shift_plan(db: Session=Depends(get_db), user=Depends(_owner_only)):
    from owner.planning import shifts
    return shifts(OwnerContext(db,user,_restaurant(db,user)))


@router.get('/planning/stock-review')
def stock_review(db: Session=Depends(get_db), user=Depends(_owner_only)):
    from owner.stock_review import review
    return review(OwnerContext(db,user,_restaurant(db,user)))


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
    """Home in one call: pulse, costing-you-money, health tiles, the six areas, coming up. The note is /home/notes."""
    return owner_home.compose_home(_context(db, user), period)


@router.get("/home/notes")
def home_notes(period: str = Query("today", pattern="^(today|7d|30d)$"), db: Session = Depends(get_db),
               user: models.User = Depends(_owner_only)):
    """LEVIII's read and the insight. Home does not wait on this."""
    return owner_home.compose_home_notes(_context(db, user), period)


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


@router.get("/report/{period}/notes")
def report_notes(period: str, month: Optional[str] = Query(None), db: Session = Depends(get_db),
                 user: models.User = Depends(_owner_only)):
    """The report insight, after the report itself. A month applies only to the monthly report."""
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
    return owner_reports.compose_report_notes(_context(db, user), period, first)


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
