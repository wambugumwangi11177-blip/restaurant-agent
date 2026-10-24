"""Team work: private approval requests, delegated tasks and an attributable feed."""
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_restaurant_or_none
from time_utils import eat_date, utcnow

router = APIRouter(prefix="/team-work", tags=["team-work"])


def owner(user):
    return user.role in (models.Role.ADMIN, models.Role.SUPERADMIN) or user.staff_role == models.StaffRole.OWNER


def scope(db, user):
    restaurant = get_restaurant_or_none(db, user)
    if not restaurant or (user.active_restaurant_id is not None and restaurant.id != user.active_restaurant_id):
        raise HTTPException(404, "Selected branch not found")
    return restaurant.id


def visible(db, user, rid):
    query = db.query(models.TeamWorkflow).filter_by(restaurant_id=rid)
    if not owner(user):
        query = query.filter(or_(models.TeamWorkflow.created_by == user.id, models.TeamWorkflow.assigned_to == user.id))
    return query


def view(row):
    return {"id": row.id, "kind": row.kind, "title": row.title, "status": row.status,
            "revision": row.revision, "created_by": row.created_by, "assigned_to": row.assigned_to,
            "due_on": row.due_on, "created_at": row.created_at, "updated_at": row.updated_at,
            "overdue": bool(row.due_on and row.due_on < eat_date(utcnow()) and row.status in ("pending", "in_progress")),
            "details": json.loads(row.payload)}


class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_key: str = Field(min_length=8, max_length=64)
    restaurant_id: int = Field(gt=0)
    kind: Literal["task", "expense_void", "spoilage"]
    title: str = Field(min_length=3, max_length=160)
    reason: str = Field(min_length=3, max_length=500)
    assigned_to: int | None = Field(default=None, gt=0)
    due_on: date | None = None
    expense_id: int | None = Field(default=None, gt=0)
    inventory_item_id: int | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)


class TransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: int = Field(ge=0)
    action: Literal["approve", "reject", "start", "complete"]
    note: str = Field(min_length=3, max_length=500)


@router.get("")
def listing(before: int | None = Query(None, gt=0), db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rid = scope(db, user)
    query = visible(db, user, rid).filter(models.TeamWorkflow.kind != "onboarding")
    if before:
        query = query.filter(models.TeamWorkflow.id < before)
    rows = query.order_by(models.TeamWorkflow.id.desc()).limit(51).all()
    return {"restaurant_id": rid, "items": [view(r) for r in rows[:50]],
            "next_before": rows[49].id if len(rows) > 50 else None}


@router.get("/people")
def people(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rid = scope(db, user)
    if not owner(user) and user.staff_role != models.StaffRole.MANAGER:
        raise HTTPException(403, "Only the owner or manager delegates work")
    rows = db.query(models.User, models.StaffMember).join(models.StaffMember, models.StaffMember.user_id == models.User.id).filter(
        models.User.tenant_id == user.tenant_id, models.User.is_active.is_(True),
        models.StaffMember.restaurant_id == rid, models.StaffMember.is_active.is_(True)).all()
    return {"items": [{"id": u.id, "name": s.name} for u, s in rows]}


@router.post("", status_code=201)
def create(body: RequestIn, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rid = scope(db, user)
    if body.restaurant_id != rid:
        raise HTTPException(409, "Branch changed. Reload before submitting.")
    key = f"team:{rid}:{user.id}:{body.request_key}"
    request = body.model_dump(mode="json", exclude={"request_key"})
    previous = db.query(models.TeamWorkflow).filter_by(request_key=key).first()
    if previous:
        if json.loads(previous.payload)["request"] != request:
            raise HTTPException(409, "Request key already used for different work")
        return view(previous)
    details = {"request": request}
    if body.kind == "task":
        if not owner(user) and user.staff_role != models.StaffRole.MANAGER:
            raise HTTPException(403, "Only the owner or manager delegates work")
        person = db.query(models.StaffMember).join(models.User, models.User.id == models.StaffMember.user_id).filter(
            models.StaffMember.restaurant_id == rid, models.StaffMember.user_id == body.assigned_to,
            models.StaffMember.is_active.is_(True), models.User.is_active.is_(True), models.User.tenant_id == user.tenant_id).first()
        if person is None:
            raise HTTPException(422, "Choose an active teammate at this branch")
    elif body.kind == "expense_void":
        if not owner(user) and user.staff_role not in (models.StaffRole.CONTROLLER, models.StaffRole.MANAGER):
            raise HTTPException(403, "Only accounting staff may propose an expense correction")
        expense = db.query(models.Expense).filter_by(id=body.expense_id, restaurant_id=rid, voided_at=None).first()
        if expense is None:
            raise HTTPException(404, "Active expense not found")
        # The entire relevant record is pinned; a later edit requires a new proposal.
        details["snapshot"] = expense_snapshot(expense)
    else:
        if not owner(user) and user.staff_role not in (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN):
            raise HTTPException(403, "Your role cannot request a stock write-off")
        item = db.query(models.InventoryItem).filter_by(id=body.inventory_item_id, restaurant_id=rid).first()
        if item is None:
            raise HTTPException(404, "Stock item not found")
        if body.quantity is None or body.quantity > (item.quantity or 0):
            raise HTTPException(422, "Quantity must be positive and no greater than recorded stock")
        details["item_name"], details["unit"] = item.item_name, item.unit
        details["on_hand"] = item.quantity or 0
    if body.kind != "task" and body.assigned_to is not None:
        raise HTTPException(422, "Approval requests go to the owner, not a teammate")
    row = models.TeamWorkflow(restaurant_id=rid, created_by=user.id, assigned_to=body.assigned_to,
        request_key=key, kind=body.kind, title=body.title, payload=json.dumps(details, sort_keys=True),
        status="pending", revision=0, due_on=body.due_on)
    db.add(row)
    try:
        db.flush()
        db.add(models.TeamWorkflowEvent(workflow_id=row.id, actor_id=user.id, action="created", note=body.reason))
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.query(models.TeamWorkflow).filter_by(request_key=key).first()
        if previous and json.loads(previous.payload)["request"] == request:
            return view(previous)
        raise HTTPException(409, "Request changed during save; reload")
    return view(row)


def expense_snapshot(expense):
    return {k: str(getattr(expense, k)) for k in ("amount_cents", "category_id", "paid_on", "method", "note", "receipt_ref", "supplier", "updated_at")}


@router.post("/{workflow_id}/transition")
def transition(workflow_id: int, body: TransitionIn, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    row = visible(db, user, scope(db, user)).filter_by(id=workflow_id).first()
    if row is None:
        raise HTTPException(404, "Work item not found")
    if row.status not in ("pending", "in_progress") or row.revision != body.revision:
        raise HTTPException(409, "This item changed; reload before acting")
    if row.kind == "task":
        if not owner(user) and row.assigned_to != user.id:
            raise HTTPException(403, "Only the assignee or owner can complete this task")
        if body.action not in ("start", "complete") or (body.action == "start" and row.status != "pending"):
            raise HTTPException(422, "Choose start or complete")
        status = "in_progress" if body.action == "start" else "completed"
    else:
        if not owner(user) or row.created_by == user.id:
            raise HTTPException(403, "A different owner must review this request")
        if body.action not in ("approve", "reject"):
            raise HTTPException(422, "Choose approve or reject")
        status = "approved" if body.action == "approve" else "rejected"
    # Compare-and-swap works on SQLite as well as PostgreSQL: simultaneous actions cannot both apply.
    updated = db.query(models.TeamWorkflow).filter_by(id=row.id, revision=body.revision, status=row.status).update(
        {"status": status, "revision": body.revision + 1, "updated_at": utcnow()}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise HTTPException(409, "This item changed; reload before acting")
    details = json.loads(row.payload)
    request = details["request"]
    if status == "approved" and row.kind == "expense_void":
        expense = db.query(models.Expense).filter_by(id=request["expense_id"], restaurant_id=row.restaurant_id).with_for_update().first()
        if expense is None or expense.voided_at is not None or expense_snapshot(expense) != details["snapshot"]:
            db.rollback()
            raise HTTPException(409, "Expense changed; submit a new proposal")
        expense.voided_at, expense.voided_by_user_id = utcnow(), user.id
        expense.void_reason = request["reason"][:200]
    if status == "approved" and row.kind == "spoilage":
        item = db.query(models.InventoryItem).filter_by(id=request["inventory_item_id"], restaurant_id=row.restaurant_id).with_for_update().first()
        if item is None or item.quantity != details["on_hand"] or request["quantity"] > (item.quantity or 0):
            db.rollback()
            raise HTTPException(409, "Stock changed; check it and submit a new request")
        item.quantity -= request["quantity"]
        db.add(models.StockMovement(inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
            quantity=request["quantity"], reason=f'waste: {request["reason"]}', performed_by_user_id=user.id, created_at=utcnow()))
    db.add(models.TeamWorkflowEvent(workflow_id=row.id, actor_id=user.id, action=status, note=body.note))
    db.commit()
    db.refresh(row)
    return view(row)


@router.get("/activity")
def activity(before: int | None = Query(None, gt=0), db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    ids = visible(db, user, scope(db, user)).with_entities(models.TeamWorkflow.id).subquery()
    query = db.query(models.TeamWorkflowEvent, models.TeamWorkflow.title).join(models.TeamWorkflow).filter(
        models.TeamWorkflowEvent.workflow_id.in_(db.query(ids.c.id)))
    if before:
        query = query.filter(models.TeamWorkflowEvent.id < before)
    rows = query.order_by(models.TeamWorkflowEvent.id.desc()).limit(51).all()
    return {"items": [{"id": event.id, "title": title, "action": event.action, "actor_id": event.actor_id,
        "note": event.note, "created_at": event.created_at} for event, title in rows[:50]],
        "next_before": rows[49][0].id if len(rows) > 50 else None}


@router.get("/options")
def options(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rid = scope(db, user)
    stock = []
    expenses = []
    if owner(user) or user.staff_role in (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN):
        stock = [{"id": i.id, "name": i.item_name, "unit": i.unit} for i in db.query(models.InventoryItem).filter_by(restaurant_id=rid).order_by(models.InventoryItem.item_name).all()]
    if owner(user) or user.staff_role in (models.StaffRole.MANAGER, models.StaffRole.CONTROLLER):
        expenses = [{"id": e.id, "name": f"{e.paid_on} · {e.note or e.supplier or e.category.name}", "amount_cents": e.amount_cents}
                    for e in db.query(models.Expense).filter_by(restaurant_id=rid, voided_at=None).order_by(models.Expense.id.desc()).limit(100).all()]
    return {"stock": stock, "expenses": expenses}
