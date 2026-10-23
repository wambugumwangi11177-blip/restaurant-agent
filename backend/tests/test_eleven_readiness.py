"""Eleven presentation gaps: exercise the live routes and the real stock/recipe sums."""
from datetime import timedelta
import io
import pytest
from PIL import Image
import auth
import models
from ai.stock_custody import _theoretical_usage_by_item
from tests.test_overview_scope import scoped_owner  # noqa: F401
from time_utils import utcnow


@pytest.fixture
def ingredients(db_session, scoped_owner):
    stock=db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    stock.quantity=8;stock.par_level=5;stock.buying_unit='crate';stock.buying_unit_factor=24
    dishes=[models.MenuItem(restaurant_id=202,name='Fish',price=65000,cost_price=26000),
            models.MenuItem(restaurant_id=202,name='Stew',price=55000,cost_price=20000)]
    db_session.add_all(dishes);db_session.flush()
    line=models.MenuIngredient(menu_item_id=dishes[0].id,inventory_item_id=stock.id,quantity_per_serving=.25,yield_fraction=.8)
    db_session.add(line);db_session.commit()
    return stock,dishes,line


def test_yield_feeds_stock_and_prep(client,db_session,scoped_owner,ingredients):
    _,h=scoped_owner;stock,dishes,line=ingredients
    order=models.Order(restaurant_id=202,total=65000,is_paid=True,status=models.OrderStatus.SERVED)
    db_session.add(order);db_session.flush()
    db_session.add(models.OrderItem(order_id=order.id,menu_item_id=dishes[0].id,quantity=45));db_session.commit()
    expected=_theoretical_usage_by_item(db_session,202,utcnow()-timedelta(days=1))
    assert expected[stock.id]==pytest.approx(14.0625)
    r=client.post('/api/v1/owner/planning/prep',headers=h,json={'dishes':[{'menu_item_id':dishes[0].id,'portions':45}]})
    assert r.status_code==200,r.text
    row=r.json()['items'][0]
    assert row['need']==14.0625 and row['buy']==11.06


def test_combo_is_the_guides_example(client,scoped_owner,ingredients):
    _,h=scoped_owner;_,dishes,_=ingredients
    r=client.post('/api/v1/owner/planning/combo',headers=h,json={'menu_item_ids':[d.id for d in dishes],'price_cents':105000})
    assert r.status_code==200,r.text
    assert r.json()['margin_pct']==56.2 and r.json()['cost_kes']==460


@pytest.mark.parametrize('path,body',[
 ('planning/prep',{'dishes':[{'menu_item_id':999999,'portions':45}]}),
 ('planning/combo',{'menu_item_ids':[999998,999999],'price_cents':105000}),
])
def test_planners_cannot_use_foreign_dishes(client,scoped_owner,path,body):
    _,h=scoped_owner
    assert client.post('/api/v1/owner/'+path,headers=h,json=body).status_code==422


def test_catalog_and_units_are_selected_branch_only(client,db_session,scoped_owner,ingredients):
    _,h=scoped_owner;stock,_,_=ingredients
    catalog=client.get('/api/v1/owner/operations/catalog',headers=h).json()
    assert [s['id'] for s in catalog['stock']]==[stock.id]
    foreign=db_session.query(models.InventoryItem).filter_by(restaurant_id=303).one()
    assert client.put(f'/api/v1/owner/operations/units/{foreign.id}',headers=h,json={'buying_unit':'crate','factor':24}).status_code==404
    assert client.put(f'/api/v1/owner/operations/units/{stock.id}',headers=h,json={'buying_unit':'crate','factor':0}).status_code==422


def test_delivery_converts_and_retry_cannot_add_stock_twice(client,db_session,scoped_owner,ingredients):
    _,h=scoped_owner;stock,_,_=ingredients
    po=db_session.query(models.PurchaseOrder).filter_by(restaurant_id=202).one()
    po.inventory_item_id=stock.id;po.quantity_ordered=60;po.unit='kg';po.status='SENT';db_session.commit()
    body={'quantity':2,'units':'buying'}
    for _ in range(2):
        r=client.post(f'/api/v1/owner/operations/deliveries/{po.id}/receive',headers=h,json=body)
        assert r.status_code==200,r.text
        assert r.json()['received']==48 and r.json()['status']=='PARTIAL'
    db_session.refresh(stock);assert stock.quantity==56
    assert client.post(f'/api/v1/owner/operations/deliveries/{po.id}/receive',headers=h,json={'quantity':3,'units':'buying'}).status_code==409
    foreign=db_session.query(models.PurchaseOrder).filter_by(restaurant_id=303).one()
    assert client.post(f'/api/v1/owner/operations/deliveries/{foreign.id}/receive',headers=h,json=body).status_code==404


def test_private_photo_upload_rejects_foreign_and_non_images(client,db_session,scoped_owner,monkeypatch,tmp_path):
    _,h=scoped_owner
    import storage
    monkeypatch.setattr(storage,'_LOCAL_ROOT',tmp_path);monkeypatch.setattr(storage,'_BACKEND','local')
    image=io.BytesIO();Image.new('RGB',(5,5)).save(image,format='PNG')
    r=client.post('/api/v1/owner/operations/receipts',headers=h,files={'file':('invoice.png',image.getvalue(),'image/png')})
    assert r.status_code==201,r.text
    ref=r.json()['receipt_ref'];assert ref.startswith('receipts/202/')
    assert client.get('/api/v1/owner/operations/receipts/'+ref.split('/')[-1],headers=h).status_code==200
    other=models.User(tenant_id=202,active_restaurant_id=303,email='foreign-photo@example.com',hashed_password='unused',role=models.Role.ADMIN)
    db_session.add(other);db_session.commit()
    other_headers={'Authorization':'Bearer '+auth.create_access_token({'sub':other.email})}
    assert client.get('/api/v1/owner/operations/receipts/'+ref.split('/')[-1],headers=other_headers).status_code==404
    assert client.get('/api/v1/owner/operations/receipts/missing.jpg',headers=h).status_code==404
    assert client.post('/api/v1/owner/operations/receipts',headers=h,files={'file':('x.jpg',b'not an image','image/jpeg')}).status_code==422
    assert client.post('/api/v1/owner/operations/receipts',headers=h,files={'file':('x.jpg',b'x'*750001,'image/jpeg')}).status_code==413


def test_expense_retry_preserves_one_ledger_entry(client,db_session,scoped_owner):
    _,h=scoped_owner
    body={'category':'gas','amount_kes':'4500.00','method':'cash','entry_key':'expense-test-123'}
    first=client.post('/api/v1/owner/money/expenses',headers=h,json=body)
    second=client.post('/api/v1/owner/money/expenses',headers=h,json=body)
    assert first.status_code==second.status_code==201,(first.text,second.text)
    assert first.json()['id']==second.json()['id']
    assert db_session.query(models.Expense).filter_by(restaurant_id=202).count()==1
    assert client.post('/api/v1/owner/money/expenses',headers=h,json={**body,'amount_kes':'5000'}).status_code==409


def test_cash_retry_and_nairobi_window(client,db_session,scoped_owner):
    _,h=scoped_owner
    body={'counted_amount_cents':1835000,'window_start':'2026-10-22T08:00:00+03:00','window_end':'2026-10-22T16:00:00+03:00','entry_key':'drawer-test-123'}
    a=client.post('/api/v1/cash-reconciliation/counts',headers=h,json=body)
    b=client.post('/api/v1/cash-reconciliation/counts',headers=h,json=body)
    assert a.status_code==b.status_code==201,(a.text,b.text)
    assert a.json()['id']==b.json()['id'] and '05:00:00' in a.json()['window_start']
    assert db_session.query(models.CashDrawerCount).filter_by(restaurant_id=202).count()==1


@pytest.mark.parametrize('path,method,body',[
 ('/api/v1/owner/planning/shifts','get',None),
 ('/api/v1/owner/planning/prep','post',{'dishes':[{'menu_item_id':1,'portions':1}]}),
 ('/api/v1/owner/planning/combo','post',{'menu_item_ids':[1,2],'price_cents':100}),
 ('/api/v1/owner/operations/catalog','get',None),
 ('/api/v1/owner/operations/units/1','put',{'buying_unit':'crate','factor':24}),
])
def test_kitchen_role_cannot_read_money_or_change_units(client,db_session,scoped_owner,path,method,body):
    user,_=scoped_owner
    user.role=models.Role.STAFF;user.staff_role=models.StaffRole.KITCHEN;db_session.commit()
    h={'Authorization':'Bearer '+auth.create_access_token({'sub':user.email})}
    r=getattr(client,method)(path,headers=h,**({'json':body} if body else {}))
    assert r.status_code==403,r.text


def test_yield_input_validation(client,scoped_owner,ingredients):
    _,h=scoped_owner;_,dishes,line=ingredients
    for yield_fraction in [0,1.1,None]:
        r=client.put(f'/api/v1/menu/{dishes[0].id}/ingredients/{line.id}',headers=h,json={'yield_fraction':yield_fraction})
        assert r.status_code==422,r.text


def test_health_uses_profit_currency_and_licence_expiry(client,scoped_owner,ingredients):
    _,h=scoped_owner
    r=client.get('/api/v1/owner/home',headers=h);assert r.status_code==200,r.text
    tiles={t['area']:t for t in r.json()['health']['tiles']}
    assert tiles['money']['unit']=='KES' and 'kept' in tiles['money']['label']
    assert tiles['store']['unit']==tiles['cash']['unit']=='KES'
    assert tiles['permits']['unit']=='days' and tiles['permits']['number'] is None
    assert tiles['permits']['status']=='unknown'


def test_health_counts_a_receipt_with_the_wrong_amount(monkeypatch):
    from types import SimpleNamespace
    from owner.health import compose
    from owner.settings import Settings
    import owner.health
    from routers import overview
    monkeypatch.setattr(owner.health,'compute_pnl',lambda *a,**kw:{})
    monkeypatch.setattr(owner.health,'owner_pnl',lambda *a,**kw:{'state':'as_entered','complete':True,'lines':[{'key':'kept','kes':15000}]})
    monkeypatch.setattr(overview,'_summarize',lambda *a,**kw:{'revenue':100000})
    ctx=SimpleNamespace(now=utcnow(),db=None,rid=1,settings=Settings(),safe=lambda key,fn:fn(),order_state=lambda **kw:{'state':'live'})
    blocks={k:{'title':k,'blocks':{},'summary':{'number':25,'unit':'%','label':'wages','word':'Fine','status':'good'}} for k in ['money','sales_dishes','store','cash','staff','permits']}
    blocks['store']['blocks']['missing']={'state':'as_entered','items':[]}
    blocks['cash']['blocks']={'shifts':{'state':'as_entered','shifts':[]},'mpesa':{'state':'as_entered','checked':{},'different_amounts':[{'sale_kes':1200,'payment_kes':1000}]}}
    blocks['staff']['blocks']['wages']={'state':'as_entered'}
    blocks['permits']['blocks']['licences']={'state':'as_entered','items':[{'name':'Health','days_left':3}]}
    tiles={t['area']:t for t in compose(ctx,blocks)['tiles']}
    assert tiles['cash']['number']==200 and tiles['cash']['status']=='bad'
    assert tiles['money']['number']==15000 and tiles['permits']['status']=='bad'


def test_migration_057_matches_the_models_and_roundtrips(tmp_path):
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).resolve().parents[1]/'alembic/versions/057_eleven_demo_readiness.py'
    spec=importlib.util.spec_from_file_location('migration_057',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=sa.create_engine(f'sqlite:///{tmp_path / "migration.db"}')
    models.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade();migration.upgrade()
            migration.downgrade();migration.upgrade()
        for table,columns in migration.FIELDS.items():
            assert {c.name for c in columns} <= {c['name'] for c in sa.inspect(conn).get_columns(table)}
    engine.dispose()
