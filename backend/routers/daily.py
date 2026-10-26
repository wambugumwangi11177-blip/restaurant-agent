"""Authenticated daily tasks, location evidence and persisted close review."""
import json
from datetime import date,datetime,time,timedelta
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,StrictInt
from sqlalchemy.orm import Session
import models
from auth import require_staff_role
from database import get_db
from routers.deps import get_or_create_restaurant
from owner import daily
from owner.settings import get_settings
from time_utils import utcnow,eat_date,EAT_OFFSET

router=APIRouter(prefix='/daily',tags=['daily-work'])
all_staff=require_staff_role(*tuple(models.StaffRole))
stock_staff=require_staff_role(models.StaffRole.MANAGER,models.StaffRole.STOCKKEEPER,models.StaffRole.CONTROLLER,models.StaffRole.KITCHEN)
stock_writers=require_staff_role(models.StaffRole.MANAGER,models.StaffRole.STOCKKEEPER,models.StaffRole.CONTROLLER)
reviewers=require_staff_role(models.StaffRole.MANAGER,models.StaffRole.CONTROLLER)

def owner(user): return user.role in (models.Role.ADMIN,models.Role.SUPERADMIN) or user.staff_role==models.StaffRole.OWNER

def item_for(db,rid,iid):
    item=db.query(models.InventoryItem).filter_by(id=iid,restaurant_id=rid).with_for_update().first()
    if not item: raise HTTPException(404,'Stock item not found')
    return item

@router.get('/team')
def branch_team(db:Session=Depends(get_db),user=Depends(reviewers)):
    rid=get_or_create_restaurant(db,user).id
    return [{'id':u.id,'name':m.name,'role':u.staff_role.value if u.staff_role else 'unassigned'} for m,u in db.query(models.StaffMember,models.User).join(models.User,models.StaffMember.user_id==models.User.id).filter(models.StaffMember.restaurant_id==rid,models.User.is_active.is_(True)).all()]

@router.get('/tasks')
def tasks(db:Session=Depends(get_db),user=Depends(all_staff)):
    rid=get_or_create_restaurant(db,user).id
    pending=db.query(models.StockTransfer).filter(models.StockTransfer.restaurant_id==rid,models.StockTransfer.status.in_([models.StockTransferStatus.PENDING,models.StockTransferStatus.REQUESTED])).count()
    disputed=db.query(models.StockTransfer).filter_by(restaurant_id=rid,status=models.StockTransferStatus.DISPUTED).count()
    day=eat_date(utcnow())
    close=db.query(models.DailyShiftClose).filter_by(restaurant_id=rid,day=day).first()
    assignments=[]
    recent=db.query(models.DailyShiftClose).filter(models.DailyShiftClose.restaurant_id==rid,models.DailyShiftClose.day<=day,models.DailyShiftClose.day>=day-timedelta(days=7)).all()
    for review in recent:
        for original in json.loads(review.snapshot).get('assignments',[]):
            a={**original,'day':review.day.isoformat()}
            submitted=db.query(models.CashDrawerCount).filter_by(restaurant_id=rid,counted_by_user_id=a['user_id'],window_start=datetime.fromisoformat(a['start']),window_end=datetime.fromisoformat(a['end'])).first() is not None
            a['submitted']=submitted
            if review.day==day or not submitted:assignments.append(a)
    role=user.staff_role.value if user.staff_role else 'owner'
    return {'day':day.isoformat(),'as_of':utcnow().isoformat()+'Z','role':role,'restaurant_id':rid,
        'stock_recording_issues':len(daily.location_issues(db,rid)),'pending_handovers':pending,'disputed_handovers':disputed,'close_status':close.status if close else 'open',
        'assignments':[a for a in assignments if owner(user) or role in ('manager','controller') or a['user_id']==user.id],
        'identity':user.id,'note':'Tasks use recorded evidence. A discrepancy is a reason to check, not a finding of theft.'}

@router.get('/stock')
def stock_list(q:str=Query('',max_length=100),page:int=Query(1,ge=1),db:Session=Depends(get_db),user=Depends(stock_staff)):
    rid=get_or_create_restaurant(db,user).id
    query=db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id==rid)
    if q.strip():query=query.filter(models.InventoryItem.item_name.ilike('%'+q.strip()+'%'))
    total=query.count();pages=max(1,(total+4)//5);page=min(page,pages)
    rows=query.order_by(models.InventoryItem.item_name,models.InventoryItem.id).offset((page-1)*5).limit(5).all()
    flagged=set(daily.location_issues(db,rid))
    return {'restaurant_id':rid,'as_of':utcnow().isoformat()+'Z','page':page,'pages':pages,'total':total,'items':[{'id':i.id,'name':i.item_name,'unit':i.unit,'on_hand':i.quantity,'needs_location_review':i.id in flagged} for i in rows]}

@router.get('/stock/{item_id}')
def stock_detail(item_id:int,db:Session=Depends(get_db),user=Depends(stock_staff)):
    rid=get_or_create_restaurant(db,user).id;item=item_for(db,rid,item_id)
    events=db.query(models.StockZoneEvent).filter_by(restaurant_id=rid,inventory_item_id=item.id).order_by(models.StockZoneEvent.id.desc()).limit(50).all()
    moves=db.query(models.StockMovement).filter_by(inventory_item_id=item.id).order_by(models.StockMovement.created_at.desc()).limit(30).all()
    batches=db.query(models.StockReceiptBatch).filter_by(restaurant_id=rid,inventory_item_id=item.id).order_by(models.StockReceiptBatch.created_at.desc()).limit(30).all()
    return {'id':item.id,'name':item.item_name,'unit':item.unit,'on_hand':item.quantity,'balances':daily.balances(db,item),
        'events':[{'id':e.id,'at':e.created_at.isoformat()+'Z','zone':e.zone,'delta':e.delta,'kind':e.kind,'actor_id':e.actor_id,**json.loads(e.details)} for e in events],
        'movements':[{'at':m.created_at.isoformat()+'Z','kind':m.movement_type.value,'quantity':m.quantity,'reason':m.reason} for m in moves],
        'batches':[{'id':b.id,'quantity_received':b.quantity,'expires_on':b.expires_on,'received_at':b.created_at,'note':'Receipt batch, not a remaining-lot balance'} for b in batches],
        'note':'Historical stock is unallocated until physically located. Receipt expiry dates describe received batches; consumption is not tracked per batch. Negative zone balances flag missing location records.'}

class EvidenceIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    restaurant_id:int
    entry_key:str=Field(min_length=8,max_length=64)
    kind:str=Field(pattern='^(waste|count)$')
    zone:str=Field(pattern='^(store|kitchen)$')
    quantity:float=Field(ge=0,le=1000000,allow_inf_nan=False)
    reason:str=Field(min_length=3,max_length=500)
    reason_code:str=Field(pattern='^(spoilage|breakage|trim|staff_meal|other|physical_count)$')
    photo_ref:str|None=None
    captured_at:datetime

@router.post('/stock/{item_id}/evidence',status_code=201)
def evidence(item_id:int,body:EvidenceIn,db:Session=Depends(get_db),user=Depends(stock_writers)):
    rid=get_or_create_restaurant(db,user).id
    if body.restaurant_id!=rid:raise HTTPException(409,'Branch changed; return to the captured branch')
    item=item_for(db,rid,item_id)
    captured=body.captured_at
    if captured.tzinfo:captured=captured.astimezone(__import__('datetime').timezone.utc).replace(tzinfo=None)
    if captured>utcnow()+timedelta(minutes=5) or captured<utcnow()-timedelta(days=7):raise HTTPException(422,'Capture time must be within seven days')
    if body.photo_ref:
        from routers.owner_operations import receipt_key
        receipt_key(body.photo_ref,rid)
    payload=body.model_dump(mode='json',exclude={'entry_key'})
    key=f'evidence:{rid}:{user.id}:{body.entry_key}'
    previous=db.query(models.StockZoneEvent).filter_by(entry_key=key).first()
    if previous:
        if json.loads(previous.details).get('request')!=payload:raise HTTPException(409,'Retry key used for different evidence')
        return {'id':previous.id,'message':'Already recorded; no duplicate movement'}
    if body.kind=='count':
        newer_move=db.query(models.StockMovement).filter(models.StockMovement.inventory_item_id==item.id,models.StockMovement.created_at>captured).first()
        newer_zone=db.query(models.StockZoneEvent).filter(models.StockZoneEvent.inventory_item_id==item.id,models.StockZoneEvent.created_at>captured).first()
        if newer_move or newer_zone:raise HTTPException(409,'Stock moved after capture. Count again.')
    balance=daily.balances(db,item)
    current=balance[body.zone]
    delta=body.quantity-current if body.kind=='count' else -body.quantity
    if body.kind=='waste' and (not body.quantity or body.quantity>max(current,0)):raise HTTPException(422,'Locate and count stock in this zone before recording waste beyond its balance')
    # First location counts assign historical unallocated stock before changing the whole-item book balance.
    allocated=min(max(delta,0),max(balance['unallocated'],0)) if body.kind=='count' else 0
    global_delta=delta-allocated
    item.quantity=(item.quantity or 0)+global_delta
    details={'request':payload,'reason':body.reason,'reason_code':body.reason_code,'photo_ref':body.photo_ref,'captured_at':captured.isoformat()+'Z','allocated_from_unknown':allocated}
    event=daily.zone_event(db,item,body.zone,delta,body.kind,user.id,key,details)
    if global_delta:
        db.add(models.StockMovement(inventory_item_id=item.id,movement_type=models.StockMovementType.ADJUST if global_delta>0 else models.StockMovementType.OUT,
            quantity=abs(global_delta),reason=('waste: ' if body.kind=='waste' else 'Physical zone count: ')+body.reason,performed_by_user_id=user.id))
    daily.reopen(db,rid,eat_date(captured),'Stock evidence added or corrected')
    db.commit();db.refresh(event)
    return {'id':event.id,'message':'Evidence recorded; original quantities and actor retained','balances':daily.balances(db,item)}

@router.get('/close/{day}')
def get_close(day:date,db:Session=Depends(get_db),user=Depends(reviewers)):
    rid=get_or_create_restaurant(db,user).id
    row=db.query(models.DailyShiftClose).filter_by(restaurant_id=rid,day=day).first()
    checks,summary=daily.day_checks(db,rid,day,get_settings(db,rid))
    return {'day':day,'status':row.status if row else 'open','version':row.version if row else 0,'checks':checks,'summary':summary,
        'history':json.loads(row.history) if row else [],'assignments':json.loads(row.snapshot).get('assignments',[]) if row else [],'can_override':owner(user)}

class ReviewIn(BaseModel):
    restaurant_id:int
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=0)
    action:str=Field(pattern='^(ready_for_review|closed|closed_with_exceptions|open)$')
    reason:str=Field(min_length=3,max_length=500)

@router.post('/close/{day}/review')
def review_close(day:date,body:ReviewIn,db:Session=Depends(get_db),user=Depends(reviewers)):
    rid=get_or_create_restaurant(db,user).id
    if body.restaurant_id!=rid:raise HTTPException(409,'Branch changed; reload before reviewing')
    if day>eat_date(utcnow()):raise HTTPException(422,'Cannot close a future day')
    row=db.query(models.DailyShiftClose).filter_by(restaurant_id=rid,day=day).with_for_update().first()
    if not row:
        row=models.DailyShiftClose(restaurant_id=rid,day=day,status='open',version=0,snapshot='{}',history='[]');db.add(row);db.flush()
    if row.version!=body.version:raise HTTPException(409,'Review changed; reload the latest checklist')
    checks,summary=daily.day_checks(db,rid,day,get_settings(db,rid))
    if body.action=='closed' and not all(c['done'] for c in checks):raise HTTPException(409,'Resolve outstanding checks or ask the owner to close with exceptions')
    if body.action=='closed_with_exceptions' and not owner(user):raise HTTPException(403,'Only the owner can authorise closing with exceptions')
    assignments=json.loads(row.snapshot).get('assignments',[])
    row.status=body.action;row.version+=1;row.reviewed_by=user.id;row.closed_at=utcnow() if body.action.startswith('closed') else None
    row.snapshot=json.dumps({'checks':checks,'summary':summary,'assignments':assignments})
    history=json.loads(row.history);history.append({'at':utcnow().isoformat()+'Z','action':body.action,'actor':user.id,'reason':body.reason,'checks':checks});row.history=json.dumps(history)
    from sqlalchemy.orm.exc import StaleDataError
    try:db.commit()
    except StaleDataError:
        db.rollback();raise HTTPException(409,'Review changed; reload the latest checklist')
    return get_close(day,db,user)

class AssignmentIn(BaseModel):
    restaurant_id:int
    user_id:int
    start:datetime
    end:datetime

@router.post('/close/{day}/assign')
def assign(day:date,body:AssignmentIn,db:Session=Depends(get_db),user=Depends(reviewers)):
    rid=get_or_create_restaurant(db,user).id
    if body.restaurant_id!=rid:raise HTTPException(409,'Branch changed; reload before assigning')
    target=db.query(models.User).join(models.StaffMember,models.StaffMember.user_id==models.User.id).filter(models.StaffMember.restaurant_id==rid,models.User.id==body.user_id,models.User.is_active.is_(True)).first()
    if not target:raise HTTPException(404,'Active staff member not found in this branch')
    start=body.start.replace(tzinfo=None)-(body.start.utcoffset() or timedelta())
    end=body.end.replace(tzinfo=None)-(body.end.utcoffset() or timedelta())
    if end<=start or eat_date(start)!=day or end-start>timedelta(hours=24):raise HTTPException(422,'Choose a valid shift window starting on this Nairobi day')
    row=db.query(models.DailyShiftClose).filter_by(restaurant_id=rid,day=day).with_for_update().first()
    if not row:row=models.DailyShiftClose(restaurant_id=rid,day=day,status='open',version=0,snapshot='{}',history='[]');db.add(row)
    snapshot=json.loads(row.snapshot);assignments=snapshot.get('assignments',[])
    if any(start<datetime.fromisoformat(a['end']) and datetime.fromisoformat(a['start'])<end for a in assignments):raise HTTPException(409,'This restaurant drawer already has an assigned overlapping count window')
    assignments.append({'user_id':target.id,'name':target.email,'start':start.isoformat(),'end':end.isoformat()});snapshot['assignments']=assignments;row.snapshot=json.dumps(snapshot);row.version+=1
    daily.reopen(db,rid,day,'Cash assignment changed');db.commit();return {'message':'Restaurant drawer window assigned; expected cash stays hidden until counted'}

class BlindCountIn(BaseModel):
    restaurant_id:int
    entry_key:str=Field(min_length=8,max_length=64)
    counted_cents:StrictInt=Field(ge=0,le=10000000000)
    start:datetime
    end:datetime

@router.post('/cash-count',status_code=201)
def blind_count(body:BlindCountIn,db:Session=Depends(get_db),user=Depends(all_staff)):
    rid=get_or_create_restaurant(db,user).id
    if body.restaurant_id!=rid:raise HTTPException(409,'Branch changed; return to the assigned branch')
    start=body.start.replace(tzinfo=None);end=body.end.replace(tzinfo=None)
    if body.start.utcoffset():start-=body.start.utcoffset()
    if body.end.utcoffset():end-=body.end.utcoffset()
    day=eat_date(start)
    row=db.query(models.DailyShiftClose).filter_by(restaurant_id=rid,day=day).first()
    assignments=json.loads(row.snapshot).get('assignments',[]) if row else []
    if not any(a['user_id']==user.id and a['start']==start.isoformat() and a['end']==end.isoformat() for a in assignments):raise HTTPException(403,'Only the person assigned to this drawer window can submit its count')
    if end>utcnow():raise HTTPException(422,'Wait until the assigned window has ended')
    from ai.cash_reconciliation.intelligence import record_drawer_count,DrawerCountError
    try:count=record_drawer_count(db,rid,user.id,body.counted_cents,start,end,entry_key=f'daily:{rid}:{user.id}:{body.entry_key}')
    except DrawerCountError as exc:raise HTTPException(409,str(exc)) from exc
    daily.reopen(db,rid,day,'Blind count submitted');db.commit()
    return {'id':count.id,'message':'Blind count recorded for accountant review'}
