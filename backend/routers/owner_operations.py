"""Small staff entry tools. Every object is resolved inside the signed-in restaurant."""
import io
import uuid
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

router = APIRouter(prefix='/owner/operations', tags=['staff-entry'])
readers = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER)
receivers = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER)
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
    return {'stock':[stock_json(i) for i in stock], 'dishes':[dict(id=d.id, name=d.name) for d in dishes]}

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
async def upload_receipt(file: UploadFile=File(...), db: Session=Depends(get_db), user=Depends(readers)):
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
def read_receipt(name: str, db: Session=Depends(get_db), user=Depends(readers)):
    rid=get_or_create_restaurant(db,user).id
    key=receipt_key(f'receipts/{rid}/{name}',rid)
    return Response(storage.load(key),media_type='image/jpeg',headers={'Cache-Control':'no-store','Content-Disposition':'inline; filename="receipt.jpg"'})

class ReceiveIn(Strict):
    quantity: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    units: Literal['counting','buying']='counting'
    invoice_ref: str | None = Field(default=None, max_length=255)

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
        return {'id':po.id,'received':po.quantity_received,'status':po.status,'invoice_ref':po.invoice_ref}
    po.invoice_ref=body.invoice_ref
    try:
        po=reorder.receive_purchase_order(db,po_id,rid,quantity,user.id)
    except reorder.PurchaseOrderError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {'id':po.id,'received':po.quantity_received,'status':po.status,'invoice_ref':po.invoice_ref}
