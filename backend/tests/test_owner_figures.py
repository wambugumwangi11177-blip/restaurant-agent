"""Each guide figure has a payload, and an empty restaurant says so."""
import auth
import models
from owner.figures import KEYS, compose
from owner.states import OwnerContext
from routers.deps import get_or_create_restaurant


def _ctx(db, suffix):
    tenant = models.Tenant(name=f"Fig{suffix}")
    db.add(tenant)
    db.commit()
    user = models.User(tenant_id=tenant.id, email=f"fig{suffix}@e.com", hashed_password=auth.get_password_hash("x"),
                       role=models.Role.ADMIN, token_version=0)
    db.add(user)
    db.commit()
    restaurant = get_or_create_restaurant(db, user)
    return OwnerContext(db, user, restaurant)


def test_every_figure_is_empty_until_there_are_records(db_session):
    figures = compose(_ctx(db_session, "empty"), {})
    assert set(figures) == set(KEYS)
    for key, payload in figures.items():
        assert payload["state"] in ("no_data", "unavailable"), key
        assert payload.get("reason")


def test_card_leg_price_ladder_and_one_order_are_in_the_payload(db_session):
    ctx = _ctx(db_session, "live")
    now = ctx.now
    db_session.add(models.MenuItem(restaurant_id=ctx.rid, name="Tea", price=15000, cost_price=4000, category="Drinks"))
    db_session.add(models.InventoryItem(restaurant_id=ctx.rid, item_name="Beef", quantity=4, unit="kg",
                                        cost_per_unit_cents=80000, low_stock_threshold=2))
    db_session.add(models.CashDrawerCount(
        restaurant_id=ctx.rid, window_start=now.replace(microsecond=0), window_end=now.replace(microsecond=0),
        expected_amount_cents=100000, counted_amount_cents=90000, counted_by_user_id=ctx.user.id, counted_at=now,
    ))
    order = models.Order(restaurant_id=ctx.rid, status=models.OrderStatus.SERVED, is_paid=True,
                         payment_method=models.PaymentMethod.MPESA, total=25000, mpesa_receipt="FIGRECEIPT1", created_at=now)
    db_session.add(order)
    db_session.commit()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=db_session.query(models.MenuItem).filter_by(restaurant_id=ctx.rid).one().id,
                                    quantity=2, unit_price=15000))
    db_session.commit()
    figures = compose(ctx, {})
    card = next(leg for leg in figures["three_way"]["legs"] if leg["key"] == "card")
    assert card["right_label"] == "Settlement not recorded"
    assert card["right_kes"] is None
    assert figures["short_count"]["short"] is True
    assert figures["short_count"]["bars"]
    assert figures["price_ladder"]["rungs"][0]["dish"] == "Tea"
    assert figures["price_tree"]["nodes"][0]["title"] == "Cost"
    assert figures["shilling"]["steps"][0]["step"] == "Order"
    assert figures["shilling"]["order_id"] == order.id
    assert any(step["step"] == "Statement" for step in figures["shilling"]["steps"])
    assert figures["pareto"]["points"][0]["cumulative_pct"] == 100.0
    assert figures["abc_calendar"]["cells"][0]["item"] == "Beef"
    assert figures["why_tree"]["drivers"]
    assert figures["stock_history"]["item"] == "Beef"
    assert figures["elasticity"]["state"] == "no_data"
    assert figures["alert_pyramid"]["state"] == "no_data"
