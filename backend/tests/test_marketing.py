"""
Marketing insights (GET /ai/marketing backing module). Verifies the read-only
offer engine turns real data into an explained, consent-aware view:
  - a lapsed regular who consented shows up as reachable and yields a win-back offer
  - the consent count and audience are surfaced
Nothing here sends anything — sending is the owner-triggered POST routes.
"""

from datetime import timedelta

import models
from ai.marketing import get_marketing_insights
from time_utils import utcnow


def _restaurant(db):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    db.add(r)
    db.commit()
    return r


def test_marketing_surfaces_consented_winback_offer(db_session):
    _restaurant(db_session)
    long_ago = utcnow() - timedelta(days=40)

    # One lapsed regular who opted in, one lapsed regular who did not.
    for phone in ("0712345678", "0722222222"):
        db_session.add(models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True, total=8000,
            customer_name="Regular", customer_phone=phone, created_at=long_ago,
        ))
    db_session.add(models.CustomerConsent(
        restaurant_id=1, customer_phone="0712345678", purpose="order_checkout",
    ))
    db_session.commit()

    out = get_marketing_insights(db_session, 1)

    # Both are lapsed, but only the consented one is reachable.
    assert out["winback"]["count"] == 2
    assert out["winback"]["reachable"] == 1
    assert out["winback"]["past_spend_cents"] == 16000
    assert out["audience"]["consented_customers"] == 1

    # The offer engine proposes a win-back campaign wired to the winback send action.
    winback_offers = [o for o in out["suggested_offers"] if o["action"] == "winback"]
    assert len(winback_offers) == 1
    assert winback_offers[0]["margin_safe"] is True
    assert "why" in winback_offers[0] and winback_offers[0]["why"]


def test_marketing_empty_restaurant_is_graceful(db_session):
    _restaurant(db_session)
    out = get_marketing_insights(db_session, 1)
    assert out["winback"]["count"] == 0
    assert out["suggested_offers"] == []
    assert out["history"] == []
    assert out["audience"]["consented_customers"] == 0
