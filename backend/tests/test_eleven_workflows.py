from datetime import datetime, time, timedelta
from types import SimpleNamespace
import pytest
import models
import schemas
from tests.test_overview_scope import scoped_owner  # noqa: F401
from owner.growth import learned_sensitivity, price_results
from domain.scheduled_prices import checkout_prices, prices, quoted_menu
from domain.pricing import build_order_lines
from time_utils import utcnow, eat_date, EAT_OFFSET


@pytest.fixture
def setup_menu(db_session, scoped_owner):
    stock=db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    supplier=db_session.query(models.Supplier).filter_by(restaurant_id=202).one()
    stock.quantity=2;stock.par_level=3;stock.cost_per_unit_cents=10000;stock.default_supplier_id=supplier.id
    dish=models.MenuItem(restaurant_id=202,name='Test stew',category='Meals',price=50000,cost_price=20000,is_available=True)
    db_session.add(dish);db_session.flush()
    db_session.add(models.MenuIngredient(menu_item_id=dish.id,inventory_item_id=stock.id,quantity_per_serving=.2,yield_fraction=.8))
    db_session.commit()
    return stock,dish


def add_sale(db,rid,dish,at,quantity,price):
    o=models.Order(restaurant_id=rid,created_at=at,total=quantity*price,is_paid=True,status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH,delivery_channel=models.DeliveryChannel.WALK_IN)
    db.add(o);db.flush();db.add(models.OrderItem(order_id=o.id,menu_item_id=dish.id,quantity=quantity,unit_price=price))


def test_forecast_to_prep_to_retry_safe_drafts(client,db_session,scoped_owner,setup_menu):
    _,h=scoped_owner;stock,dish=setup_menu
    today=eat_date(utcnow());target=today+timedelta(days=1)
    days=[today-timedelta(days=n) for n in range(1,35) if (today-timedelta(days=n)).weekday()==target.weekday()][:4]
    for day in days:
        add_sale(db_session,202,dish,datetime.combine(day,time(12))-EAT_OFFSET,8,50000)
    db_session.commit()
    r=client.get(f'/api/v1/owner/planning/forecast?on={target}',headers=h)
    assert r.status_code==200,r.text
    forecast=r.json()
    assert len(forecast['observed_days'])==4
    assert forecast['dishes'][0]['portions']==8
    body={'dishes':[{'menu_item_id':dish.id,'portions':8}],'suppliers':{},'entry_key':'market-retry-001'}
    result=client.post('/api/v1/owner/planning/market-drafts',headers=h,json=body)
    assert result.status_code==201,result.text
    ids=result.json()['purchase_order_ids']
    assert len(ids)==1
    po=db_session.get(models.PurchaseOrder,ids[0]);assert po.quantity_ordered==3 and po.total_cost==30000 and po.status=='PENDING'
    assert client.post('/api/v1/owner/planning/market-drafts',headers=h,json=body).json()==result.json()
    body['dishes'][0]['portions']=9
    assert client.post('/api/v1/owner/planning/market-drafts',headers=h,json=body).status_code==409


def test_scheduled_price_is_scoped_and_quote_survives_schedule_change(client,db_session,scoped_owner,setup_menu):
    user,h=scoped_owner;_,dish=setup_menu
    tomorrow=eat_date(utcnow())+timedelta(days=1)
    body={'menu_item_id':dish.id,'price_cents':45000,'starts_on':str(tomorrow),'explanation':'Afternoon value menu','daypart':'afternoon'}
    response=client.post('/api/v1/owner/planning/prices',headers=h,json=body)
    assert response.status_code==201,response.text
    assert client.post('/api/v1/owner/planning/prices',headers=h,json=body).status_code==409
    rule=db_session.get(models.ScheduledMenuPrice,response.json()['id'])
    rule.starts_on=eat_date(utcnow())
    rule.daypart='all';db_session.commit()
    at=utcnow()
    assert prices(db_session,202,'walk_in',at)[dish.id]==45000
    assert prices(db_session,303,'walk_in',at)=={}
    quote=quoted_menu(db_session,202,'walk_in',[dish],at)[0].price_quote
    rule.price_cents=47000;db_session.commit()
    lines=[schemas.OrderItemCreate(menu_item_id=dish.id,quantity=2,price_quote=quote)]
    resolved=checkout_prices(db_session,202,'walk_in',lines,utcnow())
    order,total=build_order_lines(lines,{dish.id:dish},prices_by_id=resolved)
    assert total==90000 and order[0].unit_price==45000
    with pytest.raises(Exception) as exc:
        checkout_prices(db_session,303,'walk_in',lines,utcnow())
    assert exc.value.status_code==409
    with pytest.raises(Exception) as exc:
        checkout_prices(db_session,202,'walk_in',[schemas.OrderItemCreate(menu_item_id=dish.id,quantity=1)],utcnow())
    assert exc.value.status_code==409


def test_daypart_surges_and_foreign_dishes_rejected(client,scoped_owner,setup_menu):
    _,h=scoped_owner;_,dish=setup_menu
    body={'menu_item_id':dish.id,'price_cents':60000,'starts_on':str(eat_date(utcnow())+timedelta(days=1)),'explanation':'Quiet afternoon menu','daypart':'afternoon'}
    assert client.post('/api/v1/owner/planning/prices',headers=h,json=body).status_code==422
    body['menu_item_id']=999999
    assert client.post('/api/v1/owner/planning/prices',headers=h,json=body).status_code==404


def test_observed_learning_replaces_assumption_only_with_evidence(client,db_session,scoped_owner,setup_menu):
    _,h=scoped_owner;_,dish=setup_menu
    now=utcnow();at=now-timedelta(days=15)
    change=models.PricingRecommendation(restaurant_id=202,menu_item_id=dish.id,recommendation_type='raise',
        current_price=50000,suggested_price=55000,status='APPROVED',actioned_at=at)
    db_session.add(change)
    for day in range(1,15):
        add_sale(db_session,202,dish,at-timedelta(days=day)+timedelta(minutes=1),10,50000)
        add_sale(db_session,202,dish,at+timedelta(days=day-1,minutes=1),9,55000)
    db_session.commit()
    result=price_results(db_session,202,now)[0]
    assert result['revenue_change_kes']==-700
    assert result['elasticity']==pytest.approx(-1.1054,abs=.001)
    assert learned_sensitivity(db_session,202,dish.id,now)==result['elasticity']
    assert learned_sensitivity(db_session,303,dish.id,now) is None
    menu=client.get('/api/v1/owner/planning/menu-review',headers=h)
    assert menu.status_code==200,menu.text
    assert menu.json()['results'][0]['elasticity']==result['elasticity']


@pytest.mark.parametrize('kind,quantity',[('waste',1),('count',1),('count',3),('issue',1)])
def test_stock_entry_retry_undo_and_branch_boundary(client,db_session,scoped_owner,setup_menu,kind,quantity):
    _,h=scoped_owner;stock,_=setup_menu
    body={'restaurant_id':202,'entry_key':f'{kind}-retry-key','kind':kind,'inventory_item_id':stock.id,'quantity':quantity,'note':'Shift test entry'}
    first=client.post('/api/v1/owner/operations/entries',headers=h,json=body)
    assert first.status_code==201,first.text
    second=client.post('/api/v1/owner/operations/entries',headers=h,json=body)
    assert second.status_code==201 and first.json()['entry_id']==second.json()['entry_id']
    db_session.refresh(stock);assert stock.quantity==(quantity if kind=='count' else 2 if kind=='issue' else 1)
    undo=client.post(f"/api/v1/owner/operations/entries/{first.json()['entry_id']}/undo",headers=h)
    assert undo.status_code==200,undo.text
    db_session.refresh(stock);assert stock.quantity==2
    if kind in ('waste','count'):
        reviewed=client.get('/api/v1/owner/planning/stock-review',headers=h).json()['items'][0]
        assert reviewed['waste_pct']==0 and reviewed['total_consumed_30d']==0
        assert reviewed['last_count'] is None
        from ai.stock_custody import _actual_usage_by_item
        assert _actual_usage_by_item(db_session,202,utcnow()-timedelta(days=1)).get(stock.id,0)==0
    body['restaurant_id']=303;body['entry_key']='wrong-branch-key'
    assert client.post('/api/v1/owner/operations/entries',headers=h,json=body).status_code==409


def test_offline_count_cannot_overwrite_later_movement(client,db_session,scoped_owner,setup_menu):
    _,h=scoped_owner;stock,_=setup_menu
    db_session.add(models.StockMovement(inventory_item_id=stock.id,movement_type=models.StockMovementType.OUT,quantity=1,reason='sale',created_at=utcnow()))
    db_session.commit()
    body={'restaurant_id':202,'entry_key':'stale-count-key','kind':'count','inventory_item_id':stock.id,'quantity':5,'note':'Offline count',
          'captured_at':(utcnow()-timedelta(hours=1)).isoformat()+'Z'}
    r=client.post('/api/v1/owner/operations/entries',headers=h,json=body)
    assert r.status_code==409,r.text
    db_session.refresh(stock);assert stock.quantity==2


def test_controller_can_count_and_issue_for_client_responsibility(client,db_session,scoped_owner,setup_menu):
    user,h=scoped_owner;stock,_=setup_menu
    user.role=models.Role.STAFF;user.staff_role=models.StaffRole.CONTROLLER;db_session.commit()
    body={'restaurant_id':202,'entry_key':'controller-key','kind':'issue','inventory_item_id':stock.id,'quantity':1,'note':'Kitchen issue by accountant'}
    assert client.post('/api/v1/owner/operations/entries',headers=h,json=body).status_code==201
    body['kind']='count';body['entry_key']='controller-count-key'
    assert client.post('/api/v1/owner/operations/entries',headers=h,json=body).status_code==201


def test_shift_attributes_statement_matching_and_only_bounded_stock(client,db_session,scoped_owner,setup_menu):
    user,h=scoped_owner;stock,dish=setup_menu
    end=utcnow()-timedelta(hours=1);start=end-timedelta(hours=8)
    db_session.add(models.CashDrawerCount(restaurant_id=202,window_start=start,window_end=end,
        expected_amount_cents=10000,counted_amount_cents=9000,counted_by_user_id=user.id))
    order=models.Order(restaurant_id=202,created_at=start+timedelta(hours=1),completed_at=start+timedelta(hours=2),
        is_paid=True,status=models.OrderStatus.SERVED,total=50000,payment_method=models.PaymentMethod.MPESA,mpesa_receipt='SHIFTTEST001')
    db_session.add(order)
    upload=models.MpesaStatementUpload(restaurant_id=202,filename='test.csv',parser='test',uploaded_by_user_id=user.id)
    db_session.add(upload);db_session.flush()
    db_session.add(models.MpesaStatementLine(restaurant_id=202,upload_id=upload.id,receipt='SHIFTTEST001',completed_at=order.completed_at,paid_in_cents=50000))
    for at,expected,counted in [(start+timedelta(minutes=1),10,10),(end-timedelta(minutes=1),8,7)]:
        db_session.add(models.StockCount(restaurant_id=202,inventory_item_id=stock.id,expected_quantity=expected,
            counted_quantity=counted,counted_by_user_id=user.id,counted_at=at))
    db_session.commit()
    r=client.get('/api/v1/owner/planning/shifts',headers=h);assert r.status_code==200,r.text
    shift=r.json()['shifts'][0]
    assert shift['mpesa_matched_kes']==500 and shift['mpesa_unmatched_kes']==0
    assert shift['mpesa_statement_complete'] is False
    assert shift['stock_gap']==100 and len(shift['stock_items'])==1
    # Without the opening physical count this cannot be called a shift loss.
    opening=db_session.query(models.StockCount).filter_by(restaurant_id=202,inventory_item_id=stock.id).order_by(models.StockCount.counted_at).first()
    db_session.delete(opening);db_session.commit()
    assert client.get('/api/v1/owner/planning/shifts',headers=h).json()['shifts'][0]['stock_gap'] is None


def test_expense_queue_cannot_land_in_a_different_branch(client,scoped_owner):
    _,h=scoped_owner
    assert client.post('/api/v1/owner/money/expenses',headers=h,json={'expected_restaurant_id':303,'entry_key':'queued-expense-01',
        'category':'gas','amount_kes':'500.00','method':'cash'}).status_code==409


def test_biggest_spend_item_is_daily_count_class():
    from ai.inventory_predictor import _apply_abc_classification
    items=_apply_abc_classification([{'id':1,'monthly_spend':900},{'id':2,'monthly_spend':70},{'id':3,'monthly_spend':30}])
    assert [i['abc_class'] for i in items]==['A','B','C']


@pytest.mark.parametrize('hour,expected',[(2,'late'),(6,'breakfast'),(11,'lunch'),(15,'afternoon'),(18,'dinner'),(22,'late')])
def test_scheduled_dayparts_use_nairobi_boundaries(hour,expected):
    from domain.scheduled_prices import daypart
    assert daypart(datetime(2026,10,23,hour)-EAT_OFFSET)==expected


def test_migration_058_roundtrip_matches_models(tmp_path):
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).resolve().parents[1]/'alembic/versions/058_eleven_workflows.py'
    spec=importlib.util.spec_from_file_location('migration_058',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=sa.create_engine(f'sqlite:///{tmp_path / "migration.db"}')
    models.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade();migration.upgrade()
        for table in ('scheduled_menu_prices','operation_entries'):
            assert set(models.Base.metadata.tables[table].columns.keys())=={c['name'] for c in sa.inspect(conn).get_columns(table)}
    engine.dispose()


def test_scheduled_discount_is_not_reported_as_an_unapproved_till_gap(db_session,scoped_owner,setup_menu):
    user,_=scoped_owner;_,dish=setup_menu
    now=utcnow()
    db_session.add(models.ScheduledMenuPrice(restaurant_id=202,menu_item_id=dish.id,channel='walk_in',daypart='all',
        price_cents=40000,starts_on=eat_date(now)-timedelta(days=2),created_at=now-timedelta(days=3),
        explanation='Approved value menu',created_by=user.id))
    for n in range(6):
        add_sale(db_session,202,dish,now-timedelta(hours=2,minutes=n),1,40000)
    db_session.commit()
    from ai.profit.intelligence import _detect_till_price_gap
    assert _detect_till_price_gap(db_session,202,{dish.id:dish},now)==[]


def test_bill_payment_retry_and_undo_keep_the_ledger_consistent(client,db_session,scoped_owner):
    user,h=scoped_owner
    categories=client.get('/api/v1/owner/money/categories',headers=h).json()['categories']
    bill=models.RecurringBill(restaurant_id=202,name='Test rent',category_id=categories[0]['id'],amount_cents=450000,
        frequency='monthly',due_day=1,start_on=eat_date(utcnow())-timedelta(days=30),is_active=True)
    db_session.add(bill);db_session.commit()
    body={'restaurant_id':202,'entry_key':'bill-test-repeat','kind':'bill','bill_id':bill.id,'note':'Rent paid by bank','method':'bank'}
    r=client.post('/api/v1/owner/operations/entries',headers=h,json=body)
    assert r.status_code==201,r.text
    eid=r.json()['expense_id']
    assert client.post('/api/v1/owner/operations/entries',headers=h,json=body).json()['expense_id']==eid
    expense=db_session.get(models.Expense,eid);assert expense.amount_cents==450000 and expense.method=='bank'
    assert client.post(f"/api/v1/owner/operations/entries/{r.json()['entry_id']}/undo",headers=h).status_code==200
    db_session.refresh(expense);assert expense.voided_at is not None and expense.voided_by_user_id==user.id
