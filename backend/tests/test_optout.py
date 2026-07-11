"""
WhatsApp opt-out (AUP §04 / DPA withdraw-consent). A customer STOP must be
recorded and honoured everywhere outbound messages are sent; START resumes.
Matching is on the normalized phone, so a STOP as "whatsapp:+2547..." suppresses
an order stored as "07...".
"""

import models
from ai.whatsapp import optout, brain
from time_utils import utcnow


def test_record_and_check_opt_out_normalizes(db_session):
    # Stored order phone shape vs. inbound WhatsApp shape — must match.
    assert optout.record_opt_out(db_session, "whatsapp:+254712345678") is True
    assert optout.is_opted_out(db_session, "0712345678") is True
    # Idempotent.
    assert optout.record_opt_out(db_session, "254712345678") is False

    row = db_session.query(models.CustomerOptOut).all()
    assert len(row) == 1
    assert row[0].customer_phone == "254712345678"


def test_start_removes_opt_out(db_session):
    optout.record_opt_out(db_session, "0712345678")
    assert optout.is_opted_out(db_session, "0712345678") is True
    assert optout.remove_opt_out(db_session, "+254712345678") is True
    assert optout.is_opted_out(db_session, "0712345678") is False


def test_send_engine_suppresses_opted_out_number(db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    db_session.add(r)
    db_session.commit()

    optout.record_opt_out(db_session, "0712345678")
    result = brain.send_whatsapp_message(
        "0712345678", "Come back for 10% off!", db=db_session,
        restaurant_id=1, message_type="campaign_winback",
    )
    assert result["status"] == "suppressed_optout"

    # And the suppression is logged (not silently dropped).
    logged = db_session.query(models.AgentMessage).filter(
        models.AgentMessage.status == "suppressed_optout"
    ).first()
    assert logged is not None


def test_winback_candidates_exclude_opted_out(db_session):
    from datetime import timedelta
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    db_session.add(r)
    db_session.commit()

    long_ago = utcnow() - timedelta(days=40)
    for phone in ("0712345678", "0722222222"):
        o = models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True, total=5000,
            customer_name="X", customer_phone=phone, created_at=long_ago,
        )
        db_session.add(o)
    db_session.commit()

    optout.record_opt_out(db_session, "0712345678")
    candidates = brain.get_winback_candidates(db_session, 1)
    phones = {c["phone"] for c in candidates}
    assert "0722222222" in phones
    assert "0712345678" not in phones


def test_winback_reachable_requires_consent_and_honours_optout(db_session):
    """A win-back is marketing: it may only reach a lapsed regular who gave
    positive consent AND hasn't opted out — the same bar broadcast_promo uses."""
    from datetime import timedelta
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    db_session.add(r)
    db_session.commit()

    long_ago = utcnow() - timedelta(days=40)
    for phone in ("0712345678", "0722222222"):
        db_session.add(models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True, total=5000,
            customer_name="X", customer_phone=phone, created_at=long_ago,
        ))
    # Only the first customer consented to marketing.
    db_session.add(models.CustomerConsent(
        restaurant_id=1, customer_phone="0712345678", purpose="order_checkout",
    ))
    db_session.commit()

    # Two lapsed candidates, but only one is a legal recipient.
    assert brain.winback_reachable(db_session, 1) == 1

    # Opting the consented one out drops the reachable audience to zero.
    optout.record_opt_out(db_session, "0712345678")
    assert brain.winback_reachable(db_session, 1) == 0


def test_stop_keyword_detection():
    assert optout.is_stop_keyword("STOP")
    assert optout.is_stop_keyword("  Unsubscribe ")
    assert not optout.is_stop_keyword("stock")
    assert optout.is_start_keyword("START")
    assert not optout.is_start_keyword("yes")
