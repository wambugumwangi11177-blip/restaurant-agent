"""Small staff entry tools. Every object is resolved inside the signed-in restaurant."""
import io
import uuid
import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from PIL import Image, UnidentifiedImageError
import models
import storage
from auth import require_staff_role
from database import get_db
from routers.deps import get_or_create_restaurant
from ai import reorder
from time_utils import utcnow, eat_date
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix='/owner/operations', tags=['staff-entry'])
readers = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER)
receivers = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER)
managers = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER)

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

def item_for(db, user, item_id):
    rid = get_or_create_restaurant(db, user).id
    item = db.query(models.InventoryItem).filter_by(id=item_id, restaurant_id=rid).first()
    if item is None:
        raise HTTPException(404, 'Stock item not found')
    return item

def stock_json(i):
    return dict(id=i.id, name=i.item_name, unit=i.unit, on_hand=i.quantity, par=i.par_level,
                buying_unit=i.buying_unit, factor=i.buying_unit_factor)

@router.get('/catalog')
def catalog(db: Session=Depends(get_db), user=Depends(readers)):
    rid = get_or_create_restaurant(db, user).id
    stock = db.query(models.InventoryItem).filter_by(restaurant_id=rid).order_by(models.InventoryItem.item_name).all()
    dishes = db.query(models.MenuItem).filter_by(restaurant_id=rid).order_by(models.MenuItem.name).all()
    return {'restaurant_id':rid,'user_id':user.id,'stock':[stock_json(i) for i in stock],
            'suppliers':[{'id':s.id,'name':s.name} for s in db.query(models.Supplier).filter_by(restaurant_id=rid).all()],
            'dishes':[dict(id=d.id, name=d.name) for d in dishes]}


class OperationIn(Strict):
    entry_key: str = Field(min_length=8,max_length=64)
    restaurant_id: int = Field(gt=0)
    kind: Literal['count','waste','issue','bill']
    inventory_item_id: int | None = None
    quantity: float = Field(default=0,ge=0,le=1000000,allow_inf_nan=False)
    bill_id: int | None = None
    note: str = Field(min_length=3,max_length=500)
    method: Literal['cash','mpesa','bank','card','other'] = 'cash'
    captured_at: datetime | None = None


@router.post('/entries',status_code=201)
def record_operation(body:OperationIn,db:Session=Depends(get_db),user=Depends(readers)):
    rid=get_or_create_restaurant(db,user).id
    if body.restaurant_id!=rid:
        raise HTTPException(409,'Branch changed. Return to the branch where this entry was captured.')
    owner=user.role in (models.Role.ADMIN,models.Role.SUPERADMIN) or user.staff_role==models.StaffRole.OWNER
    if not owner and user.staff_role==models.StaffRole.CONTROLLER and body.kind=='bill':
        raise HTTPException(403,'Use the accounting bill payment workflow for bill payments')
    if not owner and user.staff_role==models.StaffRole.STOCKKEEPER and body.kind=='bill':
        raise HTTPException(403,'A manager records bill payments')
    key=f'ops:{rid}:{user.id}:{body.entry_key}'
    payload=json.dumps(body.model_dump(mode='json',exclude={'entry_key'}),sort_keys=True)
    previous=db.query(models.OperationEntry).filter_by(entry_key=key).first()
    if previous:
        if previous.payload!=payload:
            raise HTTPException(409,'Retry key used for a different entry')
        return {**json.loads(previous.result),'entry_id':previous.id,'undone':bool(previous.undone_at)}
    now=utcnow()
    captured=body.captured_at
    if captured and captured.tzinfo:
        captured=captured.astimezone(timezone.utc).replace(tzinfo=None)
    if captured and (captured>now+timedelta(minutes=5) or captured<now-timedelta(days=7)):
        raise HTTPException(422,'Entry capture time must be within the last seven days')
    result={}
    if body.kind=='bill':
        bill=db.query(models.RecurringBill).filter_by(id=body.bill_id,restaurant_id=rid,is_active=True).with_for_update().first()
        if not bill:
            raise HTTPException(404,'Active bill not found')
        expense=models.Expense(restaurant_id=rid,category_id=bill.category_id,amount_cents=bill.amount_cents,
            paid_on=eat_date(captured or now),method=body.method,supplier=bill.supplier,note=body.note,bill_id=bill.id,
            paid_by_user_id=user.id,updated_by_user_id=user.id)
        db.add(expense);db.flush();result={'expense_id':expense.id,'message':'Bill payment recorded in the ledger.'}
    else:
        item=item_for(db,user,body.inventory_item_id)
        db.refresh(item,with_for_update=True)
        before=item.quantity or 0
        if body.kind=='count':
            if captured and db.query(models.StockMovement).filter(models.StockMovement.inventory_item_id==item.id,
                models.StockMovement.created_at>captured).first():
                raise HTTPException(409,'Stock moved after this offline count. Count again before reconciling.')
            count=models.StockCount(restaurant_id=rid,inventory_item_id=item.id,expected_quantity=before,
                counted_quantity=body.quantity,counted_by_user_id=user.id,counted_at=captured or now,notes=body.note)
            db.add(count);db.flush()
            delta=body.quantity-before;item.quantity=body.quantity
            result={'count_id':count.id,'message':'Physical count recorded. Expected quantity was hidden until saving.',
                    'expected':before,'counted':body.quantity,'difference':delta,'item_id':item.id,'delta':delta}
            if abs(delta)>1e-9:
                movement=models.StockMovement(inventory_item_id=item.id,movement_type=models.StockMovementType.ADJUST if delta>0 else models.StockMovementType.OUT,
                    quantity=abs(delta),reason='Physical count reconciliation',performed_by_user_id=user.id,created_at=now)
                db.add(movement);db.flush();result['movement_id']=movement.id
        elif body.kind=='waste':
            if body.quantity<=0 or body.quantity>before:
                raise HTTPException(422,'Waste must be positive and no more than recorded stock. Count stock first if records are wrong.')
            item.quantity=before-body.quantity
            movement=models.StockMovement(inventory_item_id=item.id,movement_type=models.StockMovementType.OUT,
                quantity=body.quantity,reason=f'waste: {body.note}',performed_by_user_id=user.id,created_at=now)
            db.add(movement);db.flush()
            result={'message':'Waste recorded and stock updated.','item_id':item.id,'delta':-body.quantity,'movement_id':movement.id}
        else:
            if body.quantity<=0:
                raise HTTPException(422,'Issue a positive quantity')
            transfer=models.StockTransfer(restaurant_id=rid,inventory_item_id=item.id,quantity=body.quantity,unit=item.unit,
                from_location='store',to_location='kitchen',status=models.StockTransferStatus.PENDING,
                initiated_by_user_id=user.id,initiated_at=utcnow(),notes=body.note)
            db.add(transfer);db.flush()
            from owner.daily import dispatch
            dispatch(db,transfer)
            result={'message':'Kitchen issue saved. A different person must confirm what arrived.','transfer_id':transfer.id}
    from owner.daily import reopen
    reopen(db,rid,eat_date(captured or now),'Staff entry recorded')
    entry=models.OperationEntry(restaurant_id=rid,user_id=user.id,entry_key=key,kind=body.kind,payload=payload,result=json.dumps(result),created_at=now)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous=db.query(models.OperationEntry).filter_by(entry_key=key).first()
        if not previous or previous.payload!=payload:
            raise HTTPException(409,'Entry changed during save; reload and review')
        return {**json.loads(previous.result),'entry_id':previous.id}
    return {**result,'entry_id':entry.id}


@router.get('/entries')
def operation_history(db:Session=Depends(get_db),user=Depends(readers)):
    rid=get_or_create_restaurant(db,user).id
    return [{'id':e.id,'kind':e.kind,'at':e.created_at.isoformat(),'by_you':e.user_id==user.id,
             'undone':bool(e.undone_at),'note':json.loads(e.payload).get('note',''),**json.loads(e.result)}
            for e in db.query(models.OperationEntry).filter_by(restaurant_id=rid).order_by(models.OperationEntry.id.desc()).limit(40).all()]


@router.post('/entries/{entry_id}/undo')
def undo_operation(entry_id:int,db:Session=Depends(get_db),user=Depends(readers)):
    rid=get_or_create_restaurant(db,user).id
    entry=db.query(models.OperationEntry).filter_by(id=entry_id,restaurant_id=rid,user_id=user.id).with_for_update().first()
    if not entry:
        raise HTTPException(404,'Your entry was not found')
    if entry.undone_at:
        return {'message':'Entry already reversed; audit retained.'}
    if utcnow()-entry.created_at>timedelta(minutes=10):
        raise HTTPException(409,'Quick undo lasts 10 minutes. Record a correction with its reason instead.')
    result=json.loads(entry.result)
    if entry.kind=='bill':
        expense=db.query(models.Expense).filter_by(id=result['expense_id'],restaurant_id=rid).first()
        if not expense or expense.voided_at:
            raise HTTPException(409,'Payment already changed')
        expense.voided_at=utcnow();expense.voided_by_user_id=user.id;expense.void_reason='Quick undo of bill entry'
    elif entry.kind=='issue':
        transfer=db.query(models.StockTransfer).filter_by(id=result['transfer_id'],restaurant_id=rid).first()
        if transfer.status!=models.StockTransferStatus.PENDING:
            raise HTTPException(409,'Kitchen already processed this issue; resolve the handover instead')
        from owner.daily import zone_event
        item=item_for(db,user,transfer.inventory_item_id)
        if db.query(models.StockZoneEvent).filter_by(entry_key=f'transfer:{transfer.id}:store').first():
            zone_event(db,item,'store',transfer.quantity,'dispatch_reversal',user.id,f'transfer:{transfer.id}:undo-store')
            zone_event(db,item,'in_transit',-transfer.quantity,'dispatch_reversal',user.id,f'transfer:{transfer.id}:undo-transit')
        db.delete(transfer)  # issued quantities and reversal remain in the journal and zone ledger
    elif entry.kind in ('count','waste'):
        item=item_for(db,user,result['item_id']);db.refresh(item,with_for_update=True)
        later=db.query(models.StockMovement).filter(models.StockMovement.inventory_item_id==item.id,
            models.StockMovement.created_at>entry.created_at).first()
        if later:
            raise HTTPException(409,'Stock moved after this entry. Record a fresh physical count instead.')
        delta=-result['delta']
        if item.quantity+delta<0:
            raise HTTPException(409,'Reversal would make stock negative; record a fresh count')
        item.quantity+=delta
        if entry.kind=='count':
            correction=models.StockCount(restaurant_id=rid,inventory_item_id=item.id,expected_quantity=item.quantity-delta,
                counted_quantity=item.quantity,counted_by_user_id=user.id,notes=f'Reversal of mistaken entry {entry.id}; original physical count retained.')
            db.add(correction);db.flush();result['reversal_count_id']=correction.id
            entry.result=json.dumps(result)
        reversal=models.StockMovement(inventory_item_id=item.id,movement_type=models.StockMovementType.ADJUST if delta>=0 else models.StockMovementType.OUT,
            quantity=abs(delta),reason=f"Reversal movement #{result.get('movement_id',0)}: {entry.kind}",performed_by_user_id=user.id)
        db.add(reversal);db.flush();result['reversal_movement_id']=reversal.id
        entry.result=json.dumps(result)
    else:
        raise HTTPException(409,'This entry cannot be undone here')
    from owner.daily import reopen
    reopen(db,rid,eat_date(entry.created_at),'Entry reversed')
    original_capture=json.loads(entry.payload).get('captured_at')
    if original_capture:
        at=datetime.fromisoformat(original_capture.replace('Z','+00:00'))
        if at.tzinfo:at=at.astimezone(timezone.utc).replace(tzinfo=None)
        reopen(db,rid,eat_date(at),'Entry captured on this day was reversed')
    entry.undone_at=utcnow();db.commit()
    return {'message':'Entry reversed. Original record and correction retained for review.'}

class UnitIn(Strict):
    buying_unit: str = Field(min_length=1, max_length=40)
    factor: float = Field(gt=0, le=1000000, allow_inf_nan=False)

@router.put('/units/{item_id}')
def set_units(item_id: int, body: UnitIn, db: Session=Depends(get_db), user=Depends(managers)):
    item = item_for(db,user,item_id)
    item.buying_unit, item.buying_unit_factor = body.buying_unit.strip(), body.factor
    if not item.buying_unit:
        raise HTTPException(422,'Name the buying unit')
    db.commit()
    return stock_json(item)

def receipt_key(ref, rid):
    # Only a server-issued basename in this restaurant's namespace, never a path or external URL.
    prefix = f'receipts/{rid}/'
    if not ref.startswith(prefix) or '/' in ref[len(prefix):] or '..' in ref or not ref.endswith('.jpg'):
        raise HTTPException(404, 'Receipt not found')
    if not storage.exists(ref):
        raise HTTPException(404, 'Receipt not found')
    return ref

@router.post('/receipts', status_code=201)
async def upload_receipt(file: UploadFile=File(...), db: Session=Depends(get_db), user=Depends(require_staff_role(models.StaffRole.MANAGER,models.StaffRole.STOCKKEEPER,models.StaffRole.CONTROLLER,models.StaffRole.KITCHEN))):
    rid = get_or_create_restaurant(db,user).id
    data = await file.read(750001)
    if len(data)>750000:
        raise HTTPException(413,'Photo must be smaller than 750 KB')
    try:
        image = Image.open(io.BytesIO(data))
        if image.width*image.height > 16000000:
            raise HTTPException(422,'Photo is too large; resize it first')
        image.load()
        image = image.convert('RGB')
        image.thumbnail((1600,1600))
        out=io.BytesIO(); image.save(out,format='JPEG',quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422,'Use a valid image photo') from None
    key=storage.save(out.getvalue(),f'receipts/{rid}/{uuid.uuid4().hex}.jpg','image/jpeg')
    return {'receipt_ref':key}

@router.get('/receipts/{name}')
def read_receipt(name: str, db: Session=Depends(get_db), user=Depends(require_staff_role(models.StaffRole.MANAGER,models.StaffRole.STOCKKEEPER,models.StaffRole.CONTROLLER,models.StaffRole.KITCHEN))):
    rid=get_or_create_restaurant(db,user).id
    key=receipt_key(f'receipts/{rid}/{name}',rid)
    return Response(storage.load(key),media_type='image/jpeg',headers={'Cache-Control':'no-store','Content-Disposition':'inline; filename="receipt.jpg"'})

class ReceiveIn(Strict):
    quantity: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    units: Literal['counting','buying']='counting'
    invoice_ref: str | None = Field(default=None, max_length=255)
    expires_on: date | None = None

@router.post('/deliveries/{po_id}/receive')
def receive(po_id: int, body: ReceiveIn, db: Session=Depends(get_db), user=Depends(receivers)):
    rid=get_or_create_restaurant(db,user).id
    po=db.query(models.PurchaseOrder).filter_by(id=po_id,restaurant_id=rid).with_for_update().first()
    if po is None:
        raise HTTPException(404,'Purchase order not found')
    item=item_for(db,user,po.inventory_item_id)
    if body.units=='buying' and (not item.buying_unit or po.unit!=item.unit):
        raise HTTPException(422,'Set buying units first; the order must use this item’s counting unit')
    quantity=body.quantity*(item.buying_unit_factor if body.units=='buying' else 1)
    if body.invoice_ref:
        receipt_key(body.invoice_ref,rid)
    if po.status in ('PARTIAL','DELIVERED'):
        if po.quantity_received!=quantity or (body.invoice_ref and po.invoice_ref!=body.invoice_ref):
            raise HTTPException(409,'This delivery was already recorded with different details')
        return receipt_result(db,po,item,user,body.expires_on)
    po.invoice_ref=body.invoice_ref
    try:
        po=reorder.receive_purchase_order(db,po_id,rid,quantity,user.id,expires_on=body.expires_on)
    except reorder.PurchaseOrderError as exc:
        raise HTTPException(400,str(exc)) from exc
    return receipt_result(db,po,item,user,body.expires_on)


def receipt_result(db,po,item,user,expires_on):
    batch=db.query(models.StockReceiptBatch).filter_by(purchase_order_id=po.id,restaurant_id=po.restaurant_id).first()
    if batch and batch.expires_on!=expires_on and expires_on is not None:
        raise HTTPException(409,'Receipt batch already recorded with a different expiry')
    # Historical received orders without batch evidence remain unallocated; never infer a past location on retry.
    return {'id':po.id,'received':po.quantity_received,'status':po.status,'invoice_ref':po.invoice_ref}
