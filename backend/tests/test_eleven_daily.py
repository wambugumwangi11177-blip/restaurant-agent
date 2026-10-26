from datetime import datetime,time,timedelta
import json
import pytest
import auth,models
from tests.test_overview_scope import scoped_owner
from time_utils import utcnow,eat_date,EAT_OFFSET
from owner import daily

def staff(db,role,rid=202):
 u=models.User(tenant_id=101,active_restaurant_id=rid,email=f'{role.value}-{rid}@daily.test',hashed_password='unused',role=models.Role.STAFF,staff_role=role,is_active=True)
 db.add(u);db.flush();db.add(models.StaffMember(restaurant_id=rid,user_id=u.id,name=role.value));db.commit()
 return u,{'Authorization':'Bearer '+auth.create_access_token({'sub':u.email})}

def stock(db):return db.query(models.InventoryItem).filter_by(restaurant_id=202).one()

def test_independent_handover_retry_and_zone_conservation(client,db_session,scoped_owner):
 user,h=scoped_owner;item=stock(db_session);item.quantity=10;db_session.commit()
 accountant,ah=staff(db_session,models.StaffRole.CONTROLLER)
 r=client.post('/api/v1/stock/transfers',headers=ah,json={'inventory_item_id':item.id,'quantity':4,'unit':'kg'})
 assert r.status_code==201,r.text
 tid=r.json()['id']
 assert client.post(f'/api/v1/stock/transfers/{tid}/confirm',headers=ah,json={'confirmed_quantity':4}).status_code==400
 chef,ch=staff(db_session,models.StaffRole.KITCHEN)
 r=client.post(f'/api/v1/stock/transfers/{tid}/confirm',headers=ch,json={'confirmed_quantity':3.8})
 assert r.status_code==200,r.text
 assert r.json()['status']=='disputed'
 assert client.post(f'/api/v1/stock/transfers/{tid}/confirm',headers=ch,json={'confirmed_quantity':3.8}).status_code==200
 db_session.refresh(item);b=daily.balances(db_session,item)
 assert b['store']==-4 and b['kitchen']==3.8 and b['in_transit']==pytest.approx(.2)
 assert sum(b.values())==pytest.approx(item.quantity)
 assert db_session.query(models.StockZoneEvent).filter_by(inventory_item_id=item.id).count()==4


def test_location_count_waste_photo_scope_and_idempotency(client,db_session,scoped_owner):
 _,h=scoped_owner;item=stock(db_session);item.quantity=10;db_session.commit()
 body={'restaurant_id':202,'entry_key':'count-store-0001','kind':'count','zone':'store','quantity':8,'reason':'Morning shelf count','reason_code':'physical_count','captured_at':utcnow().isoformat()+'Z'}
 r=client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=body)
 assert r.status_code==201,r.text
 assert r.json()['balances']=={'store':8,'kitchen':0,'in_transit':0,'unallocated':2}
 assert client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=body).status_code==201
 body.update(entry_key='waste-store-0001',kind='waste',quantity=1,reason_code='spoilage',reason='Spoiled onions')
 assert client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=body).status_code==201
 db_session.refresh(item);assert item.quantity==9
 body['entry_key']='foreign-photo-0001';body['photo_ref']='receipts/303/private.jpg'
 assert client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=body).status_code==404
 foreign=db_session.query(models.InventoryItem).filter_by(restaurant_id=303).one()
 assert client.get(f'/api/v1/daily/stock/{foreign.id}',headers=h).status_code==404


def test_clean_close_needs_all_checks_override_owner_and_changes_reopen(client,db_session,scoped_owner):
 _,h=scoped_owner;day=eat_date(utcnow());path=f'/api/v1/daily/close/{day}'
 review=client.get(path,headers=h);assert review.status_code==200,review.text
 accountant,ah=staff(db_session,models.StaffRole.CONTROLLER)
 body={'restaurant_id':202,'version':0,'action':'closed','reason':'Reviewed records'}
 assert client.post(path+'/review',headers=ah,json=body).status_code==409
 body['action']='closed_with_exceptions'
 assert client.post(path+'/review',headers=ah,json=body).status_code==403
 r=client.post(path+'/review',headers=h,json=body);assert r.status_code==200,r.text
 assert r.json()['status']=='closed_with_exceptions'
 item=stock(db_session);db_session.add(models.StockMovement(inventory_item_id=item.id,movement_type=models.StockMovementType.OUT,quantity=.1,performed_by_user_id=accountant.id,reason='Corrected entry'));db_session.commit()
 result=client.get(path,headers=h).json();assert result['status']=='open'
 assert any(e['action']=='reopened' for e in result['history'])


def test_waiter_assigned_count_is_blind_and_cannot_read_other_tasks(client,db_session,scoped_owner):
 _,h=scoped_owner;waiter,wh=staff(db_session,models.StaffRole.WAITER)
 yesterday=eat_date(utcnow())-timedelta(days=1);start=datetime.combine(yesterday,time(8))-EAT_OFFSET;end=start+timedelta(hours=8)
 path=f'/api/v1/daily/close/{yesterday}'
 r=client.post(path+'/assign',headers=h,json={'restaurant_id':202,'user_id':waiter.id,'start':start.isoformat()+'Z','end':end.isoformat()+'Z'});assert r.status_code==200,r.text
 pending=client.get('/api/v1/daily/tasks',headers=wh).json()['assignments'];assert len(pending)==1 and pending[0]['day']==str(yesterday) and not pending[0]['submitted']
 body={'restaurant_id':202,'entry_key':'waiter-count-0001','start':start.isoformat()+'Z','end':end.isoformat()+'Z','counted_cents':0}
 r=client.post('/api/v1/daily/cash-count',headers=wh,json=body);assert r.status_code==201,r.text
 assert 'expected' not in r.text
 assert client.get(path,headers=wh).status_code==403
 assert client.get('/api/v1/daily/stock/1',headers=wh).status_code==403


def test_exact_shared_cost_period_and_missing_values(client,db_session,scoped_owner):
 _,h=scoped_owner
 block=client.get('/api/v1/owner/area/money',headers=h).json()['blocks']['cost_dials']
 if 'period' in block:
  assert block['period']['label']=='Last 30 calendar days'
  assert block['prime_cost_pct'] is None or block['prime_cost_pct']==pytest.approx(block['food_cost_pct']+block['wages_pct'],abs=.2)


def test_greeting_does_not_compute_a_health_score(client,scoped_owner):
 _,h=scoped_owner
 for greeting in ['hii','hello','habari','hello there']:
  r=client.post('/api/v1/owner/ask',headers=h,json={'question':greeting})
  assert r.status_code==200,r.text
  assert r.json()['rows']==[] and r.json()['topic']=='conversation'


def test_complete_restaurant_day_keeps_one_stock_and_money_record(client,db_session,scoped_owner):
 from ai.order_stock import deduct_ingredients_for_order
 from ai.stock_custody import _actual_usage_by_item
 owner,h=scoped_owner;item=stock(db_session);item.quantity=0;item.cost_per_unit_cents=10000
 supplier=db_session.query(models.Supplier).filter_by(restaurant_id=202).one()
 po=models.PurchaseOrder(restaurant_id=202,inventory_item_id=item.id,supplier_id=supplier.id,quantity_ordered=10,unit='kg',cost_per_unit=10000,total_cost=100000,status='SENT')
 db_session.add(po);db_session.commit()
 body={'quantity':10,'expires_on':(eat_date(utcnow())+timedelta(days=3)).isoformat()}
 r=client.post(f'/api/v1/owner/operations/deliveries/{po.id}/receive',headers=h,json=body);assert r.status_code==200,r.text
 assert client.post(f'/api/v1/owner/operations/deliveries/{po.id}/receive',headers=h,json=body).status_code==200
 db_session.refresh(item);assert item.quantity==10
 transfer=client.post('/api/v1/stock/transfers',headers=h,json={'inventory_item_id':item.id,'quantity':4,'unit':'kg'}).json()
 chef,ch=staff(db_session,models.StaffRole.KITCHEN)
 assert client.post(f"/api/v1/stock/transfers/{transfer['id']}/confirm",headers=ch,json={'confirmed_quantity':4}).status_code==200
 dish=models.MenuItem(restaurant_id=202,name='Daily stew',category='Meals',price=50000,cost_price=20000);db_session.add(dish);db_session.flush()
 db_session.add(models.MenuIngredient(menu_item_id=dish.id,inventory_item_id=item.id,quantity_per_serving=.5,yield_fraction=1));db_session.flush()
 order=models.Order(restaurant_id=202,table_number=1,total=100000,is_paid=True,status=models.OrderStatus.SERVED,payment_method=models.PaymentMethod.CASH,created_at=utcnow()-timedelta(minutes=1));db_session.add(order);db_session.flush()
 line=models.OrderItem(order_id=order.id,menu_item_id=dish.id,quantity=2,unit_price=50000);db_session.add(line);db_session.flush();db_session.refresh(order)
 deduct_ingredients_for_order(db_session,order,owner.id);db_session.commit()
 deduct_ingredients_for_order(db_session,order,owner.id);db_session.commit()
 waste={'restaurant_id':202,'entry_key':'journey-waste-0001','kind':'waste','zone':'kitchen','quantity':.2,'reason':'Spoiled after preparation','reason_code':'spoilage','captured_at':utcnow().isoformat()+'Z'}
 r=client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=waste);assert r.status_code==201,r.text
 db_session.refresh(item);assert item.quantity==pytest.approx(8.8)
 b=daily.balances(db_session,item);assert b['store']==6 and b['kitchen']==pytest.approx(2.8) and b['unallocated']==pytest.approx(0)
 usage=_actual_usage_by_item(db_session,202,utcnow()-timedelta(days=1));assert usage[item.id]==1 # internal handover and explained waste are not recipe consumption
 assert db_session.query(models.StockReceiptBatch).filter_by(purchase_order_id=po.id).count()==1
 assert client.get(f'/api/v1/daily/stock/{item.id}',headers=ch).json()['batches'][0]['expires_on']==body['expires_on']
 # Continue the same day through physical and blind cash counts, independent accounting review and the owner report.
 count={'restaurant_id':202,'entry_key':'journey-final-count','kind':'count','inventory_item_id':item.id,'quantity':8.8,'note':'Full item count after service'}
 assert client.post('/api/v1/owner/operations/entries',headers=h,json=count).status_code==201
 waiter,wh=staff(db_session,models.StaffRole.WAITER);_,ah=staff(db_session,models.StaffRole.CONTROLLER)
 day=eat_date(utcnow());start=datetime.combine(day,time())-EAT_OFFSET;end=utcnow();path=f'/api/v1/daily/close/{day}'
 assert client.post(path+'/assign',headers=ah,json={'restaurant_id':202,'user_id':waiter.id,'start':start.isoformat()+'Z','end':end.isoformat()+'Z'}).status_code==200
 cash={'restaurant_id':202,'entry_key':'journey-blind-cash','counted_cents':100000,'start':start.isoformat()+'Z','end':end.isoformat()+'Z'}
 r=client.post('/api/v1/daily/cash-count',headers=wh,json=cash);assert r.status_code==201,r.text
 checklist=client.get(path,headers=ah).json();assert all(c['done'] for c in checklist['checks']),checklist
 ready=client.post(path+'/review',headers=ah,json={'restaurant_id':202,'version':checklist['version'],'action':'ready_for_review','reason':'Stock and cash independently reviewed'})
 assert ready.status_code==200,ready.text
 closed=client.post(path+'/review',headers=h,json={'restaurant_id':202,'version':ready.json()['version'],'action':'closed','reason':'All required records reviewed'})
 assert closed.status_code==200 and closed.json()['status']=='closed',closed.text
 home=client.get('/api/v1/owner/home',headers=h).json();report=client.get('/api/v1/owner/report/daily',headers=h).json()
 assert report['day_close']['status']=='closed'
 assert home['pulse']['sales_today']==next(section for section in report['sections'] if section['key']=='sales')['sales']==1000
 count.update(entry_key='journey-count-correction',quantity=9,note='Late audited count correction')
 assert client.post('/api/v1/owner/operations/entries',headers=h,json=count).status_code==201
 reopened=client.get(path,headers=h).json();assert reopened['status']=='open' and any(a['action']=='closed' for a in reopened['history'])



def test_complete_clean_close_is_persisted_with_all_required_evidence(client,db_session,scoped_owner):
 _,h=scoped_owner;day=eat_date(utcnow())-timedelta(days=1);lo=datetime.combine(day,time())-EAT_OFFSET;hi=lo+timedelta(days=1)
 item=stock(db_session)
 located={'restaurant_id':202,'entry_key':'clean-close-located','kind':'count','zone':'store','quantity':item.quantity,'reason':'All stock located in store','reason_code':'physical_count','captured_at':(lo+timedelta(hours=12)).isoformat()+'Z'}
 r=client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=located);assert r.status_code==201,r.text
 db_session.add(models.StockCount(restaurant_id=202,inventory_item_id=item.id,expected_quantity=1,counted_quantity=1,counted_by_user_id=scoped_owner[0].id,counted_at=lo+timedelta(hours=12),notes='Full item count at close'))
 db_session.add(models.CashDrawerCount(restaurant_id=202,expected_amount_cents=0,counted_amount_cents=0,counted_by_user_id=scoped_owner[0].id,window_start=lo,window_end=hi,counted_at=hi,notes='No cash sales recorded'))
 db_session.commit()
 r=client.post(f'/api/v1/daily/close/{day}/review',headers=h,json={'restaurant_id':202,'version':0,'action':'closed','reason':'Every recorded check reviewed'})
 assert r.status_code==200,r.text
 data=r.json();assert data['status']=='closed' and all(c['done'] for c in data['checks'])
 assert client.get(f'/api/v1/daily/close/{day}',headers=h).json()['history'][-1]['action']=='closed'


def test_stale_location_count_after_dispatch_is_rejected(client,db_session,scoped_owner):
 _,h=scoped_owner;item=stock(db_session);captured=utcnow()-timedelta(minutes=1)
 assert client.post('/api/v1/stock/transfers',headers=h,json={'inventory_item_id':item.id,'quantity':1,'unit':'kg'}).status_code==201
 body={'restaurant_id':202,'entry_key':'stale-count-0001','kind':'count','zone':'store','quantity':8,'reason':'Offline shelf count','reason_code':'physical_count','captured_at':captured.isoformat()+'Z'}
 r=client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=body)
 assert r.status_code==409 and 'moved after capture' in r.text


def test_unexplained_statement_payment_cannot_be_a_clean_day(db_session,scoped_owner):
 from owner.settings import get_settings
 _,_=scoped_owner;day=eat_date(utcnow())-timedelta(days=1);lo=datetime.combine(day,time())-EAT_OFFSET
 upload=models.MpesaStatementUpload(restaurant_id=202,filename='local-scenario.csv',parser='test',line_count=1)
 db_session.add(upload);db_session.flush()
 db_session.add(models.MpesaStatementLine(restaurant_id=202,upload_id=upload.id,receipt='UNEXPLAINED',completed_at=lo+timedelta(hours=12),paid_in_cents=10000))
 db_session.commit()
 checks,_=daily.day_checks(db_session,202,day,get_settings(db_session,202))
 assert not next(c for c in checks if c['key']=='mpesa')['done']


def test_simultaneous_confirmation_commits_one_result(client,db_session,scoped_owner):
 from concurrent.futures import ThreadPoolExecutor
 from threading import Barrier
 from sqlalchemy.orm import sessionmaker
 from ai.stock_custody import confirm_transfer,TransferConfirmError
 _,h=scoped_owner;chef,_=staff(db_session,models.StaffRole.KITCHEN)
 tid=client.post('/api/v1/stock/transfers',headers=h,json={'inventory_item_id':stock(db_session).id,'quantity':1,'unit':'kg'}).json()['id']
 factory=sessionmaker(bind=db_session.get_bind());barrier=Barrier(2);uid=chef.id
 def confirm():
  with factory() as session:
   barrier.wait(timeout=10)
   try:return confirm_transfer(session,tid,202,uid,1).id
   except TransferConfirmError:
    session.rollback();return None
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:confirm(),range(2)))
 assert tid in results
 db_session.expire_all()
 assert db_session.get(models.StockTransfer,tid).status==models.StockTransferStatus.CONFIRMED
 assert db_session.query(models.StockZoneEvent).filter(models.StockZoneEvent.entry_key.in_([f'transfer:{tid}:arrival-out',f'transfer:{tid}:arrival-in'])).count()==2
 assert db_session.query(models.StockMovement).filter(models.StockMovement.reason.in_(['Transfer to kitchen','Transfer received from store'])).count()==2


def test_late_nairobi_assigned_count_uses_its_actual_day(client,db_session,scoped_owner):
 _,h=scoped_owner;waiter,wh=staff(db_session,models.StaffRole.WAITER)
 day=eat_date(utcnow())-timedelta(days=1)
 start=f'{day}T22:00:00+03:00';end=f'{day}T23:00:00+03:00'
 r=client.post(f'/api/v1/daily/close/{day}/assign',headers=h,json={'restaurant_id':202,'user_id':waiter.id,'start':start,'end':end});assert r.status_code==200,r.text
 r=client.post('/api/v1/daily/cash-count',headers=wh,json={'restaurant_id':202,'entry_key':'late-nairobi-window','counted_cents':0,'start':start,'end':end});assert r.status_code==201,r.text


def test_staff_location_list_is_scoped_and_unlocated_dispatch_blocks_clean_close(client,db_session,scoped_owner):
 _,h=scoped_owner;_,ah=staff(db_session,models.StaffRole.CONTROLLER);_,wh=staff(db_session,models.StaffRole.WAITER);_,ch=staff(db_session,models.StaffRole.KITCHEN)
 item=stock(db_session);assert client.post('/api/v1/stock/transfers',headers=ah,json={'inventory_item_id':item.id,'quantity':1,'unit':'litres'}).status_code==422
 r=client.get('/api/v1/daily/stock',headers=ah);assert r.status_code==200 and [x['id'] for x in r.json()['items']]==[item.id]
 assert client.get('/api/v1/daily/stock',headers=wh).status_code==403
 tid=client.post('/api/v1/stock/transfers',headers=ah,json={'inventory_item_id':item.id,'quantity':1,'unit':'kg'}).json()['id']
 assert client.post(f'/api/v1/stock/transfers/{tid}/confirm',headers=ch,json={'confirmed_quantity':1}).status_code==200
 checks=client.get('/api/v1/daily/close/'+str(eat_date(utcnow())),headers=h).json()['checks']
 assert not next(c for c in checks if c['key']=='locations')['done']
 assert next(c for c in checks if c['key']=='handovers')['done']
 assert client.get('/api/v1/daily/stock',headers=ah).json()['items'][0]['needs_location_review']


def test_ambiguous_conversation_asks_for_context_instead_of_unrelated_health(client,scoped_owner):
 _,h=scoped_owner
 r=client.post('/api/v1/owner/ask',headers=h,json={'question':'I have a question'})
 assert r.status_code==200 and r.json()['topic']=='conversation' and r.json()['rows']==[]


def test_undo_of_an_offline_count_reopens_its_original_capture_day(client,db_session,scoped_owner):
 _,h=scoped_owner;item=stock(db_session);captured=utcnow()-timedelta(days=1);day=eat_date(captured)
 body={'restaurant_id':202,'entry_key':'offline-day-count','kind':'count','inventory_item_id':item.id,'quantity':item.quantity,'note':'Offline full-item count','captured_at':captured.isoformat()+'Z'}
 r=client.post('/api/v1/owner/operations/entries',headers=h,json=body);assert r.status_code==201,r.text
 entry_id=r.json()['entry_id'];path=f'/api/v1/daily/close/{day}'
 r=client.post(path+'/review',headers=h,json={'restaurant_id':202,'version':0,'action':'closed_with_exceptions','reason':'Original records reviewed with missing cash evidence'});assert r.status_code==200,r.text
 r=client.post(f'/api/v1/owner/operations/entries/{entry_id}/undo',headers=h);assert r.status_code==200,r.text
 assert client.get(path,headers=h).json()['status']=='open'
 assert db_session.get(models.OperationEntry,entry_id).undone_at is not None


def test_unallocated_remainder_remains_a_recording_exception(client,db_session,scoped_owner):
 _,h=scoped_owner;item=stock(db_session);item.quantity=10;db_session.commit()
 for zone,qty in [('store',8),('kitchen',0)]:
  body={'restaurant_id':202,'entry_key':'partial-location-'+zone,'kind':'count','zone':zone,'quantity':qty,'reason':'Physical location count','reason_code':'physical_count','captured_at':utcnow().isoformat()+'Z'}
  r=client.post(f'/api/v1/daily/stock/{item.id}/evidence',headers=h,json=body);assert r.status_code==201,r.text
 assert item.id in daily.location_issues(db_session,202)
 r=client.post('/api/v1/owner/operations/entries',headers=h,json={'restaurant_id':202,'entry_key':'unallocated-full-count','kind':'count','inventory_item_id':item.id,'quantity':8,'note':'Total confirmed across all locations'})
 assert r.status_code==201,r.text
 db_session.refresh(item)  # HTTP writes commit in a separate session.
 assert item.id not in daily.location_issues(db_session,202)
