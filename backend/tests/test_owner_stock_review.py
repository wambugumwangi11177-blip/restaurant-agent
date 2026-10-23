from datetime import timedelta
import models
from tests.test_overview_scope import scoped_owner  # noqa: F401
from time_utils import utcnow


def test_stock_review_real_values_waste_prices_and_scope(client, db_session, scoped_owner):
    _, headers = scoped_owner
    item = db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    item.quantity = 2.125
    item.cost_per_unit_cents = 12345
    now = utcnow()
    for qty, reason in [(8, 'sale'), (2, 'waste')]:
        db_session.add(models.StockMovement(inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
                                            quantity=qty, reason=reason, created_at=now-timedelta(days=1)))
    supplier = db_session.query(models.Supplier).filter_by(restaurant_id=202).one()
    for days, price, unit in [(10, 10000, 'kg'), (1, 12000, 'kg'), (0, 500000, 'crate')]:
        db_session.add(models.PurchaseOrder(restaurant_id=202, supplier_id=supplier.id, inventory_item_id=item.id,
            quantity_ordered=10, quantity_received=10, unit=unit, cost_per_unit=price,
            status='DELIVERED', delivered_at=now-timedelta(days=days)))
    db_session.commit()
    response = client.get('/api/v1/owner/planning/stock-review', headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [i['id'] for i in data['items']] == [item.id]
    assert data['value_kes'] == 262.33
    assert data['items'][0]['waste_pct'] == 20
    assert data['items'][0]['count_overdue'] is True
    assert len(data['supplier_prices']) == 1
    assert data['supplier_prices'][0]['change_pct'] == 20
    assert data['supplier_prices'][0]['unit'] == 'kg'


def test_stock_review_negative_and_unknown_cost_not_invented(client, db_session, scoped_owner):
    _, headers = scoped_owner
    item = db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    item.quantity = -8
    item.cost_per_unit_cents = 0
    db_session.commit()
    data = client.get('/api/v1/owner/planning/stock-review', headers=headers).json()
    assert data['value_kes'] == 0
    assert data['items'][0]['negative_book_stock'] is True
    assert data['items'][0]['cost_missing'] is True
    assert data['entered_up_to'] is None


def test_fractional_units_waste_percentage(client, db_session, scoped_owner):
    _, headers = scoped_owner
    item = db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    for qty, reason in [(.3, 'sale'), (.2, 'waste')]:
        db_session.add(models.StockMovement(inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
            quantity=qty, reason=reason, created_at=utcnow()-timedelta(hours=1)))
    db_session.commit()
    data = client.get('/api/v1/owner/planning/stock-review', headers=headers).json()
    assert data['items'][0]['waste_pct'] == 40
