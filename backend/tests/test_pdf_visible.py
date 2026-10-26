"""Client guide gaps: whole-P&L price illustration and the prime-cost dial."""
from datetime import timedelta
import models
from tests.test_overview_scope import scoped_owner
from time_utils import utcnow

def seed(db):
    dish=models.MenuItem(restaurant_id=202,name="Guide dish",category="Meals",price=50000,cost_price=20000,is_available=True)
    db.add(dish);db.flush()
    for rid,qty,paid,status in [(202,3,True,models.OrderStatus.SERVED),(202,8,True,models.OrderStatus.CANCELLED),(202,9,False,models.OrderStatus.SERVED),(303,12,True,models.OrderStatus.SERVED)]:
        order=models.Order(restaurant_id=rid,table_number=1,total=qty*50000,is_paid=paid,status=status,created_at=utcnow()-timedelta(minutes=1))
        db.add(order);db.flush();db.add(models.OrderItem(order_id=order.id,menu_item_id=dish.id,quantity=qty,unit_price=50000))
    db.commit();return dish

def test_price_change_lands_in_sales_and_profit_only(client,db_session,scoped_owner):
    _,headers=scoped_owner;dish=seed(db_session)
    before=client.get('/api/v1/owner/money/pnl?period=month',headers=headers).json()
    r=client.post('/api/v1/owner/planning/price-impact',headers=headers,json={'menu_item_id':dish.id,'new_price_cents':55000})
    assert r.status_code==200,r.text
    data=r.json();assert data['portions']==3 and data['extra_sales_kes']==150
    lines={r['key']:r for r in data['rows']}
    for key in ['sales','left_after_ingredients','kept']:assert lines[key]['change_kes']==150
    for key in ['ingredients','wages','other_costs']:
        assert lines[key]['change_kes']==0
        assert lines[key]['before_pct']>=0 and lines[key]['after_pct']>=0
    after=client.get('/api/v1/owner/money/pnl?period=month',headers=headers).json()
    assert before['lines']==after['lines']
    db_session.refresh(dish);assert dish.price==50000

def test_prime_cost_is_food_plus_wages_and_has_its_saved_target(client,db_session,scoped_owner):
    _,headers=scoped_owner;seed(db_session)
    block=client.get('/api/v1/owner/area/money',headers=headers).json()['blocks']['cost_dials']
    assert block['prime_cost_pct']==round(block['food_cost_pct']+block['wages_pct'],2)
    assert block['prime_cost_target_pct']>0
    assert any(a['setting']=='prime_cost_target_pct' for a in block['assumptions'])

def test_price_impact_cannot_read_another_branch_dish(client,db_session,scoped_owner):
    _,headers=scoped_owner
    d=models.MenuItem(restaurant_id=203,name='Other branch',category='Meals',price=50000,cost_price=20000)
    db_session.add(d);db_session.commit()
    assert client.post('/api/v1/owner/planning/price-impact',headers=headers,json={'menu_item_id':d.id,'new_price_cents':55000}).status_code==404


def test_price_simulation_uses_shared_engine_and_does_not_save(client, db_session, scoped_owner):
    from ai.simulation.engine import simulate_price_change
    _, headers = scoped_owner
    dish = seed(db_session)
    expected = simulate_price_change(db_session, 202, dish.id, 55000)
    response = client.post('/api/v1/owner/planning/price-simulation', headers=headers, json={'menu_item_id': dish.id, 'new_price_cents': 55000})
    assert response.status_code == 200, response.text
    data = response.json()
    rows = {r['key']: r for r in data['rows']}
    assert data['state'] == 'assumption'
    assert rows['sales']['after'] == expected['projected']['monthly_revenue_cents'] / 100
    assert rows['contribution']['after'] == expected['projected']['monthly_profit_cents'] / 100
    assert data['demand_change_pct'] == expected['deltas']['sales_pct']
    db_session.refresh(dish)
    assert dish.price == 50000


def test_price_simulation_rejects_foreign_dish_and_fractional_cents(client, db_session, scoped_owner):
    _, headers = scoped_owner
    dish = models.MenuItem(restaurant_id=203, name='Private dish', category='Meals', price=50000, cost_price=20000)
    db_session.add(dish); db_session.commit()
    assert client.post('/api/v1/owner/planning/price-simulation', headers=headers, json={'menu_item_id': dish.id, 'new_price_cents': 55000}).status_code == 404
    assert client.post('/api/v1/owner/planning/price-simulation', headers=headers, json={'menu_item_id': dish.id, 'new_price_cents': 55000.5}).status_code == 422


def test_price_simulation_never_treats_missing_cost_as_free(client, db_session, scoped_owner):
    _, headers = scoped_owner
    dish = seed(db_session); dish.cost_price = None; db_session.commit()
    data = client.post('/api/v1/owner/planning/price-simulation', headers=headers, json={'menu_item_id': dish.id, 'new_price_cents': 55000}).json()
    assert all(row['after'] is None for row in data['rows'] if row['key'] in ('contribution','margin'))
    assert any('cost is missing' in note for note in data['notes'])
