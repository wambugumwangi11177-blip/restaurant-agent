"""/api/v1/owner/money/* — the money ledger: cost categories, expenses, recurring bills, licences (docs/v2/SPEC.md S3.1).

Owners, managers and controllers (the accountant) may read and write; every other staff role gets 403. Everything is
scoped to the caller's own tenant and active restaurant (routers/deps.py) — there is no restaurant id anywhere in this API,
so there is none to forge, and an id in a URL that is not this restaurant's is a 404.

Money crosses this edge as a decimal KES amount with at most two places and is stored as integer cents. An expense's day is
a Nairobi calendar date. Nothing is deleted: an expense is voided (who, when, why), a bill or licence is switched off.
Observer-mode deployments block this whole prefix with the rest of /owner (observer_mode.py).
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from auth import require_staff_role
from database import get_db
from owner import settings as owner_settings
from owner.money import bills as bill_rules
from owner.money import categories as cats
from owner.money.ledger import (LICENCE_MAX_DATE, LICENCE_MIN_DATE, MAX_KES, check_entry_date, nairobi_today, parse_money, to_cents,
                                to_kes)
from owner.money.licences import licence_status
from routers.deps import get_restaurant_or_none
from time_utils import utcnow

router = APIRouter(prefix="/owner/money", tags=["owner-money"])

_roles = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.CONTROLLER)

Money = Annotated[Decimal, BeforeValidator(parse_money), Field(gt=0, le=MAX_KES, decimal_places=2)]
MoneyOrZero = Annotated[Decimal, BeforeValidator(parse_money), Field(ge=0, le=MAX_KES, decimal_places=2)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Ref = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Method = Literal["cash", "mpesa", "bank", "card", "other"]
Frequency = Literal["monthly", "weekly", "yearly"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── shared ───────────────────────────────────────────────────────────────────

def _restaurant(db: Session, user: models.User) -> models.Restaurant:
    restaurant = get_restaurant_or_none(db, user)
    if restaurant is None:
        raise HTTPException(404, "Restaurant not found")
    return restaurant


def _person(u: Optional[models.User]) -> Optional[dict]:
    return None if u is None else {"id": u.id, "email": u.email}


def _cat_json(c: models.ExpenseCategory) -> dict:
    return {"id": c.id, "key": c.key, "name": c.name, "pnl_line": c.pnl_line, "is_fixed": c.is_fixed, "is_standard": c.is_standard,
            "is_active": c.is_active}


def _category(db: Session, rid: int, key: str, *, active_only: bool = True) -> models.ExpenseCategory:
    cats.ensure_categories(db, rid)
    c = db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == rid, models.ExpenseCategory.key == key).first()
    if c is None:
        raise HTTPException(422, f"Unknown cost category {key!r}. See GET /owner/money/categories.")
    if active_only and not c.is_active:
        raise HTTPException(422, f"The cost category {c.name!r} is switched off.")
    return c


def _date(day: date) -> date:
    try:
        return check_entry_date(day)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _cents(amount: Decimal) -> int:
    try:
        return to_cents(amount)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ── categories ───────────────────────────────────────────────────────────────

class CategoryIn(Strict):
    name: Name
    pnl_line: Literal["premises", "utilities", "staff", "fees", "operations", "marketing", "licences"]
    is_fixed: bool = False


class CategoryPatch(Strict):
    name: Optional[Name] = None
    pnl_line: Optional[Literal["premises", "utilities", "staff", "fees", "operations", "marketing", "licences"]] = None
    is_fixed: Optional[bool] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


@router.get("/categories")
def list_categories(include_inactive: bool = False, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """The cost lines (the Kenyan restaurant P&L lines plus the owner's own). The standard ones are created on first use."""
    rid = _restaurant(db, user).id
    cats.ensure_categories(db, rid)
    q = db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == rid)
    if not include_inactive:
        q = q.filter(models.ExpenseCategory.is_active.is_(True))
    rows = q.order_by(models.ExpenseCategory.is_standard.desc(), models.ExpenseCategory.sort_order, models.ExpenseCategory.id).all()
    db.commit()
    return {"categories": [_cat_json(c) for c in rows], "pnl_lines": [{"key": k, "name": cats.PNL_LINE_NAMES[k]} for k in cats.PNL_LINES]}


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    cats.ensure_categories(db, rid)
    key = cats.slug(body.name)
    if not key:
        raise HTTPException(422, "Give the cost line a name with letters or numbers in it.")
    if db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == rid, models.ExpenseCategory.key == key).first():
        raise HTTPException(409, "You already have a cost line with that name.")
    c = models.ExpenseCategory(restaurant_id=rid, key=key, name=body.name, pnl_line=body.pnl_line, is_fixed=body.is_fixed,
                               is_standard=False, is_active=True, sort_order=1000)
    db.add(c)
    db.commit()
    return _cat_json(c)


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryPatch, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    c = db.query(models.ExpenseCategory).filter(models.ExpenseCategory.id == category_id, models.ExpenseCategory.restaurant_id == rid).first()
    if c is None:
        raise HTTPException(404, "Cost line not found")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and cats.slug(changes["name"]) != c.key:
        clash = db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == rid,
                                                        func.lower(models.ExpenseCategory.name) == changes["name"].lower(),
                                                        models.ExpenseCategory.id != c.id).first()
        if clash:
            raise HTTPException(409, "You already have a cost line with that name.")
    for field, value in changes.items():
        setattr(c, field, value)
    db.commit()
    return _cat_json(c)


# ── expenses ─────────────────────────────────────────────────────────────────

class ExpenseIn(Strict):
    category: str
    amount_kes: Money
    paid_on: Optional[date] = None
    method: Method = "cash"
    supplier: Short = ""
    note: Note = ""
    receipt_ref: Optional[Ref] = None


class ExpensePatch(Strict):
    category: Optional[str] = None
    amount_kes: Optional[Money] = None
    paid_on: Optional[date] = None
    method: Optional[Method] = None
    supplier: Optional[Short] = None
    note: Optional[Note] = None
    receipt_ref: Optional[Ref] = None

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


class VoidIn(Strict):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


def _expense_json(e: models.Expense) -> dict:
    voided = None if e.voided_at is None else {"at": e.voided_at.isoformat(), "by": _person(e.voided_by), "reason": e.void_reason}
    return {"id": e.id, "category": {"id": e.category.id, "key": e.category.key, "name": e.category.name, "pnl_line": e.category.pnl_line},
            "amount_kes": to_kes(e.amount_cents), "paid_on": e.paid_on.isoformat(), "method": e.method, "supplier": e.supplier, "note": e.note,
            "receipt_ref": e.receipt_ref, "bill_id": e.bill_id, "paid_by": _person(e.paid_by), "created_at": e.created_at.isoformat(),
            "updated_at": e.updated_at.isoformat(), "voided": voided}


def _find_expense(db: Session, rid: int, expense_id: int) -> models.Expense:
    e = db.query(models.Expense).filter(models.Expense.id == expense_id, models.Expense.restaurant_id == rid).first()
    if e is None:
        raise HTTPException(404, "Expense not found")
    return e


@router.get("/expenses")
def list_expenses(from_: Optional[date] = Query(None, alias="from"), to: Optional[date] = None, category: Optional[str] = None,
                  include_voided: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """Newest first. `from` and `to` are Nairobi days, both ends included. Voided entries are left out unless asked for."""
    rid = _restaurant(db, user).id
    filters = [models.Expense.restaurant_id == rid]
    if not include_voided:
        filters.append(models.Expense.voided_at.is_(None))
    if from_ is not None:
        filters.append(models.Expense.paid_on >= from_)
    if to is not None:
        filters.append(models.Expense.paid_on <= to)
    if category is not None:
        filters.append(models.Expense.category_id == _category(db, rid, category, active_only=False).id)
    count, total = db.query(func.count(models.Expense.id), func.coalesce(func.sum(models.Expense.amount_cents), 0)).filter(
        *filters, models.Expense.voided_at.is_(None)).one()
    rows = db.query(models.Expense).filter(*filters).order_by(models.Expense.paid_on.desc(), models.Expense.id.desc()).offset(offset).limit(limit).all()
    if include_voided:
        count = db.query(func.count(models.Expense.id)).filter(*filters).scalar()
    return {"items": [_expense_json(e) for e in rows], "count": int(count), "total_kes": to_kes(int(total)), "limit": limit, "offset": offset}


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    cat = _category(db, rid, body.category)
    now = utcnow()
    e = models.Expense(restaurant_id=rid, category_id=cat.id, amount_cents=_cents(body.amount_kes),
                       paid_on=_date(body.paid_on or nairobi_today()), method=body.method, supplier=body.supplier, note=body.note,
                       receipt_ref=body.receipt_ref, paid_by_user_id=user.id, created_at=now, updated_at=now, updated_by_user_id=user.id)
    db.add(e)
    db.commit()
    return _expense_json(e)


@router.get("/expenses/{expense_id}")
def read_expense(expense_id: int, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    return _expense_json(_find_expense(db, _restaurant(db, user).id, expense_id))


@router.patch("/expenses/{expense_id}")
def update_expense(expense_id: int, body: ExpensePatch, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    e = _find_expense(db, rid, expense_id)
    if e.voided_at is not None:
        raise HTTPException(409, "This expense was voided and can no longer be changed.")
    changes = body.model_dump(exclude_unset=True)
    if "category" in changes:
        e.category_id = _category(db, rid, changes.pop("category")).id
    if "amount_kes" in changes:
        if changes["amount_kes"] is None:
            raise HTTPException(422, "an amount in shillings is required")
        e.amount_cents = _cents(changes.pop("amount_kes"))
    if "paid_on" in changes:
        if changes["paid_on"] is None:
            raise HTTPException(422, "a date is required")
        e.paid_on = _date(changes.pop("paid_on"))
    for field in ("method", "supplier", "note"):
        if field in changes:
            if changes[field] is None:
                raise HTTPException(422, f"{field} cannot be empty")
            setattr(e, field, changes.pop(field))
    if "receipt_ref" in changes:
        e.receipt_ref = changes.pop("receipt_ref")
    e.updated_at, e.updated_by_user_id = utcnow(), user.id
    db.commit()
    return _expense_json(e)


@router.delete("/expenses/{expense_id}")
def void_expense(expense_id: int, body: VoidIn, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """Void an expense: it leaves every list and total, the row stays, and who/when/why are kept."""
    e = _find_expense(db, _restaurant(db, user).id, expense_id)
    if e.voided_at is not None:
        raise HTTPException(409, "This expense was already voided.")
    e.voided_at, e.voided_by_user_id, e.void_reason = utcnow(), user.id, body.reason
    db.commit()
    return _expense_json(e)


# ── recurring bills ──────────────────────────────────────────────────────────

class BillIn(Strict):
    name: Name
    category: str
    amount_kes: Money
    frequency: Frequency
    due_day: int
    due_month: Optional[int] = None
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    supplier: Short = ""
    note: Note = ""


class BillPatch(Strict):
    name: Optional[Name] = None
    category: Optional[str] = None
    amount_kes: Optional[Money] = None
    frequency: Optional[Frequency] = None
    due_day: Optional[int] = None
    due_month: Optional[int] = None
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    supplier: Optional[Short] = None
    note: Optional[Note] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


class PayIn(Strict):
    amount_kes: Optional[Money] = None
    paid_on: Optional[date] = None
    method: Method = "cash"
    note: Note = ""


def _bill_json(b: models.RecurringBill, today: date) -> dict:
    due = bill_rules.next_due(b, today) if b.is_active else None
    return {"id": b.id, "name": b.name, "category": {"id": b.category.id, "key": b.category.key, "name": b.category.name},
            "amount_kes": to_kes(b.amount_cents), "frequency": b.frequency, "due_day": b.due_day, "due_month": b.due_month,
            "start_on": b.start_on.isoformat(), "end_on": b.end_on.isoformat() if b.end_on else None, "supplier": b.supplier, "note": b.note,
            "is_active": b.is_active, "next_due_on": due.isoformat() if due else None}


def _find_bill(db: Session, rid: int, bill_id: int) -> models.RecurringBill:
    b = db.query(models.RecurringBill).filter(models.RecurringBill.id == bill_id, models.RecurringBill.restaurant_id == rid).first()
    if b is None:
        raise HTTPException(404, "Bill not found")
    return b


def _check_bill(frequency: str, due_day: int, due_month: Optional[int], start_on: date, end_on: Optional[date]) -> None:
    try:
        bill_rules.check_rule(frequency, due_day, due_month)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if end_on is not None and end_on < start_on:
        raise HTTPException(422, "a bill cannot end before it starts")


@router.get("/bills")
def list_bills(include_inactive: bool = False, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """In the order they next fall due."""
    rid = _restaurant(db, user).id
    q = db.query(models.RecurringBill).filter(models.RecurringBill.restaurant_id == rid)
    if not include_inactive:
        q = q.filter(models.RecurringBill.is_active.is_(True))
    today = nairobi_today()
    rows = [_bill_json(b, today) for b in q.all()]
    rows.sort(key=lambda b: (b["next_due_on"] is None, b["next_due_on"] or "", b["id"]))
    return {"bills": rows}


@router.post("/bills", status_code=201)
def create_bill(body: BillIn, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    cat = _category(db, rid, body.category)
    today = nairobi_today()
    start = body.start_on or today
    _check_bill(body.frequency, body.due_day, body.due_month, start, body.end_on)
    now = utcnow()
    b = models.RecurringBill(restaurant_id=rid, category_id=cat.id, name=body.name, amount_cents=_cents(body.amount_kes), frequency=body.frequency,
                             due_day=body.due_day, due_month=body.due_month, start_on=start, end_on=body.end_on, supplier=body.supplier,
                             note=body.note, is_active=True, created_at=now, updated_at=now)
    db.add(b)
    db.commit()
    return _bill_json(b, today)


@router.patch("/bills/{bill_id}")
def update_bill(bill_id: int, body: BillPatch, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    b = _find_bill(db, rid, bill_id)
    changes = body.model_dump(exclude_unset=True)
    merged = {"frequency": b.frequency, "due_day": b.due_day, "due_month": b.due_month, "start_on": b.start_on, "end_on": b.end_on}
    for field in merged:
        if field in changes:
            merged[field] = changes[field]
    if merged["frequency"] is None or merged["due_day"] is None or merged["start_on"] is None:
        raise HTTPException(422, "frequency, due_day and start_on cannot be empty")
    _check_bill(merged["frequency"], merged["due_day"], merged["due_month"], merged["start_on"], merged["end_on"])
    if "category" in changes:
        b.category_id = _category(db, rid, changes.pop("category")).id
    if "amount_kes" in changes:
        if changes["amount_kes"] is None:
            raise HTTPException(422, "an amount in shillings is required")
        b.amount_cents = _cents(changes.pop("amount_kes"))
    for field in ("name", "supplier", "note", "is_active"):
        if field in changes:
            if changes[field] is None:
                raise HTTPException(422, f"{field} cannot be empty")
            setattr(b, field, changes[field])
    b.frequency, b.due_day, b.due_month, b.start_on, b.end_on = (merged[k] for k in ("frequency", "due_day", "due_month", "start_on", "end_on"))
    b.updated_at = utcnow()
    db.commit()
    return _bill_json(b, nairobi_today())


@router.post("/bills/{bill_id}/pay", status_code=201)
def pay_bill(bill_id: int, body: PayIn, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """Record that the bill was paid: an expense in the bill's category, linked to the bill."""
    rid = _restaurant(db, user).id
    b = _find_bill(db, rid, bill_id)
    if not b.is_active:
        raise HTTPException(409, "This bill is switched off.")
    now = utcnow()
    e = models.Expense(restaurant_id=rid, category_id=b.category_id, amount_cents=_cents(body.amount_kes) if body.amount_kes else b.amount_cents,
                       paid_on=_date(body.paid_on or nairobi_today()), method=body.method, supplier=b.supplier, note=body.note or "",
                       bill_id=b.id, paid_by_user_id=user.id, created_at=now, updated_at=now, updated_by_user_id=user.id)
    db.add(e)
    db.commit()
    return _expense_json(e)


# ── licences ─────────────────────────────────────────────────────────────────

class LicenceIn(Strict):
    name: Name
    issuer: Short = ""
    expires_on: date
    cost_kes: Optional[MoneyOrZero] = None
    document_ref: Optional[Ref] = None
    note: Note = ""

    @field_validator("expires_on")
    @classmethod
    def _sane(cls, v: date) -> date:
        if not (LICENCE_MIN_DATE <= v <= LICENCE_MAX_DATE):
            raise ValueError("expiry date out of range")
        return v


class LicencePatch(Strict):
    name: Optional[Name] = None
    issuer: Optional[Short] = None
    expires_on: Optional[date] = None
    cost_kes: Optional[MoneyOrZero] = None
    document_ref: Optional[Ref] = None
    note: Optional[Note] = None
    is_active: Optional[bool] = None

    @field_validator("expires_on")
    @classmethod
    def _sane(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and not (LICENCE_MIN_DATE <= v <= LICENCE_MAX_DATE):
            raise ValueError("expiry date out of range")
        return v

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


def _licence_json(l: models.Licence, today: date, warning_days: int) -> dict:
    days_left, status = licence_status(l.expires_on, today, warning_days)
    return {"id": l.id, "name": l.name, "issuer": l.issuer, "expires_on": l.expires_on.isoformat(), "days_left": days_left, "status": status,
            "cost_kes": to_kes(l.cost_cents), "document_ref": l.document_ref, "note": l.note, "is_active": l.is_active}


def _find_licence(db: Session, rid: int, licence_id: int) -> models.Licence:
    l = db.query(models.Licence).filter(models.Licence.id == licence_id, models.Licence.restaurant_id == rid).first()
    if l is None:
        raise HTTPException(404, "Licence not found")
    return l


@router.get("/licences")
def list_licences(include_inactive: bool = False, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """Soonest expiry first. 'expiring' is within the owner's licence warning days (a setting, default 14)."""
    rid = _restaurant(db, user).id
    q = db.query(models.Licence).filter(models.Licence.restaurant_id == rid)
    if not include_inactive:
        q = q.filter(models.Licence.is_active.is_(True))
    warn, today = owner_settings.get_settings(db, rid).licence_warning_days, nairobi_today()
    return {"licences": [_licence_json(l, today, warn) for l in q.order_by(models.Licence.expires_on, models.Licence.id).all()], "warning_days": warn}


@router.post("/licences", status_code=201)
def create_licence(body: LicenceIn, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    now = utcnow()
    l = models.Licence(restaurant_id=rid, name=body.name, issuer=body.issuer, expires_on=body.expires_on,
                       cost_cents=None if body.cost_kes is None else _cents(body.cost_kes), document_ref=body.document_ref, note=body.note,
                       is_active=True, created_at=now, updated_at=now)
    db.add(l)
    db.commit()
    return _licence_json(l, nairobi_today(), owner_settings.get_settings(db, rid).licence_warning_days)


@router.patch("/licences/{licence_id}")
def update_licence(licence_id: int, body: LicencePatch, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    rid = _restaurant(db, user).id
    l = _find_licence(db, rid, licence_id)
    changes = body.model_dump(exclude_unset=True)
    if "cost_kes" in changes:
        value = changes.pop("cost_kes")
        l.cost_cents = None if value is None else _cents(value)
    for field in ("name", "issuer", "expires_on", "note", "is_active"):
        if field in changes:
            if changes[field] is None:
                raise HTTPException(422, f"{field} cannot be empty")
            setattr(l, field, changes[field])
    if "document_ref" in changes:
        l.document_ref = changes["document_ref"]
    l.updated_at = utcnow()
    db.commit()
    return _licence_json(l, nairobi_today(), owner_settings.get_settings(db, rid).licence_warning_days)
