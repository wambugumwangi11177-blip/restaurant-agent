"""Resumable setup review. Recorded rows are evidence, never proof of a POS connection."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import models
from auth import require_staff_role
from database import get_db
from routers.team_workflows import scope

router = APIRouter(prefix='/owner/setup', tags=['owner-setup'])
_owner = require_staff_role(models.StaffRole.OWNER)


def steps(db, rid):
    def count(model):
        return db.query(model).filter_by(restaurant_id=rid).count()
    recipes = db.query(models.MenuIngredient).join(models.MenuItem, models.MenuItem.id == models.MenuIngredient.menu_item_id).filter(models.MenuItem.restaurant_id == rid).count()
    return [
        {'key': 'menu', 'title': 'Menu, prices and recipes', 'count': count(models.MenuItem), 'detail': f'{recipes} recipe ingredient lines recorded. Check portions, costs and raw yield with the chef.', 'href': '/planning'},
        {'key': 'team', 'title': 'People and permissions', 'count': count(models.StaffMember), 'detail': 'Check each person’s role and branch. Have them sign in and complete one real entry.', 'href': '/dashboard/staff'},
        {'key': 'stock', 'title': 'Suppliers and opening stock', 'count': count(models.StockCount), 'detail': f'{count(models.Supplier)} suppliers recorded. A stock balance is not a physical opening count.', 'href': '/entries'},
        {'key': 'money', 'title': 'Costs, bills and permits', 'count': count(models.Expense), 'detail': f'{count(models.RecurringBill)} recurring bills and {count(models.Licence)} licences recorded. Review missing categories with the accountant.', 'href': '/home#area-money'},
        {'key': 'targets', 'title': 'Agree the owner’s targets', 'count': count(models.RestaurantSettings), 'detail': 'Review food-cost, margin, cash and stock tolerances together. Defaults are not client approval.', 'href': '/home#area-permits'},
        {'key': 'source', 'title': 'Verify Eleven’s till and statements', 'count': count(models.Order), 'detail': f'{count(models.MpesaStatementUpload)} statement uploads recorded. Reconcile totals to the real source with Sam; sample orders do not prove an integration.', 'href': '/home#area-cash'},
    ]


@router.get('')
def status(db: Session = Depends(get_db), user=Depends(_owner)):
    rid = scope(db, user)
    rows = db.query(models.TeamWorkflow).filter_by(restaurant_id=rid, kind='onboarding').all()
    reviews = {json.loads(r.payload)['step']: {'by': r.created_by, 'at': r.created_at, 'note': json.loads(r.payload)['note']} for r in rows}
    return {'restaurant_id': rid, 'steps': [{**s, 'review': reviews.get(s['key'])} for s in steps(db, rid)],
            'notice': 'Reviews record what an owner checked; they do not certify deployment, import compatibility or financial accuracy.'}


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    restaurant_id: int = Field(gt=0)
    note: str = Field(min_length=10, max_length=500)


@router.post('/{step}/review')
def review(step: str, body: ReviewIn, db: Session = Depends(get_db), user=Depends(_owner)):
    rid = scope(db, user)
    if body.restaurant_id != rid:
        raise HTTPException(409, 'Branch changed; reload setup')
    titles = {s['key']: s['title'] for s in steps(db, rid)}
    if step not in titles:
        raise HTTPException(404, 'Setup step not found')
    key = f'setup:{rid}:{step}'
    existing = db.query(models.TeamWorkflow).filter_by(request_key=key).first()
    if existing:
        return {'reviewed': True, 'at': existing.created_at}
    row = models.TeamWorkflow(restaurant_id=rid, created_by=user.id, request_key=key,
        kind='onboarding', title=titles[step], payload=json.dumps({'step': step, 'note': body.note}),
        status='completed', revision=0)
    db.add(row)
    try:
        db.flush()
        db.add(models.TeamWorkflowEvent(workflow_id=row.id, actor_id=user.id, action='reviewed', note=body.note))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(models.TeamWorkflow).filter_by(request_key=key).first()
        if not existing:
            raise
        return {'reviewed': True, 'at': existing.created_at}
    return {'reviewed': True, 'at': row.created_at}
