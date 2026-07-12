"""
Covers the pricing-approval loop that was previously unreachable from the UI
(GET /ai/pricing returned id-less recs; approve/reject needed a persisted id, and
nothing ever created one — so ROI "profit captured" could never leave zero).

sync_pending_recommendations() is the bridge: it idempotently materializes the
read-only analysis into PENDING PricingRecommendation rows (each with a real id),
which the approve endpoint then turns into a live price change + captured profit.
"""

import models
from ai.pricing.recommendations import (
    sync_pending_recommendations,
    approve_recommendation,
    reject_recommendation,
    PENDING,
    EXPIRED,
)
from ai.roi.savings import get_roi_savings


def _seed(db):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    item = models.MenuItem(id=1, restaurant_id=1, name="Burger", price=50000, is_available=True)
    db.add_all([r, item])
    db.commit()
    return r, item


def _rec(item_id=1, rtype="REPRICE", suggested=60000, impact=12000):
    """A computed-analysis recommendation dict (the shape get_pricing_intelligence emits)."""
    return {
        "item_id": item_id,
        "item_name": "Burger",
        "type": rtype,
        "current_price": 50000,
        "suggested_price": suggested,
        "reason": "Margin below floor",
        "when": "All times",
        "monthly_impact_cents": impact,
        "recommendation_strength": 85,
    }


def test_sync_materializes_and_assigns_id(db_session):
    _seed(db_session)
    out = sync_pending_recommendations(db_session, 1, [_rec()])

    assert len(out) == 1
    assert isinstance(out[0]["id"], int)          # UI can now act on it
    assert out[0]["status"] == PENDING
    rows = db_session.query(models.PricingRecommendation).all()
    assert len(rows) == 1 and rows[0].status == PENDING


def test_sync_is_idempotent_no_duplicates(db_session):
    _seed(db_session)
    first = sync_pending_recommendations(db_session, 1, [_rec()])
    second = sync_pending_recommendations(db_session, 1, [_rec()])

    # Same logical rec → same persisted row reused, not a second insert.
    assert first[0]["id"] == second[0]["id"]
    assert db_session.query(models.PricingRecommendation).count() == 1


def test_sync_updates_numbers_in_place(db_session):
    _seed(db_session)
    rec_id = sync_pending_recommendations(db_session, 1, [_rec(suggested=60000)])[0]["id"]
    sync_pending_recommendations(db_session, 1, [_rec(suggested=65000, impact=15000)])

    row = db_session.get(models.PricingRecommendation, rec_id)
    assert row.suggested_price == 65000          # kept in lock-step with analysis
    assert row.monthly_impact_cents == 15000


def test_sync_expires_recs_no_longer_recommended(db_session):
    _seed(db_session)
    rec_id = sync_pending_recommendations(db_session, 1, [_rec()])[0]["id"]

    out = sync_pending_recommendations(db_session, 1, [])   # analysis no longer flags it
    assert out == []
    assert db_session.get(models.PricingRecommendation, rec_id).status == EXPIRED


def test_approval_updates_price_and_feeds_roi(db_session):
    _seed(db_session)
    rec_id = sync_pending_recommendations(db_session, 1, [_rec(suggested=60000, impact=12000)])[0]["id"]

    result = approve_recommendation(db_session, rec_id, 1, approved_by="owner@test.com")
    assert result["success"] is True

    # Live menu price moved to the suggested price.
    assert db_session.get(models.MenuItem, 1).price == 60000

    # ROI "profit captured" now reflects the approval — the whole point.
    roi = get_roi_savings(db_session, 1)
    assert roi["money_captured"]["recommendations_approved"] == 1
    assert roi["money_captured"]["monthly_impact_cents"] == 12000
    assert roi["money_captured"]["all_time_approved"] == 1


def test_rejected_rec_drops_off_and_captures_nothing(db_session):
    _seed(db_session)
    rec_id = sync_pending_recommendations(db_session, 1, [_rec()])[0]["id"]

    reject_recommendation(db_session, rec_id, 1, reason="not now")
    assert db_session.get(models.PricingRecommendation, rec_id).status == "REJECTED"
    assert db_session.get(models.MenuItem, 1).price == 50000   # price unchanged

    roi = get_roi_savings(db_session, 1)
    assert roi["money_captured"]["recommendations_approved"] == 0


def test_roi_exposes_economics_and_projection_shape(db_session):
    _seed(db_session)
    roi = get_roi_savings(db_session, 1)

    # New ROI enrichments are always present and well-formed on an empty tenant.
    assert "economics" in roi and "projection" in roi
    assert roi["economics"]["roi_multiple"] is None          # no AI spend yet → honest None
    assert roi["economics"]["value_delivered_cents"] == 0
    assert roi["projection"]["annual_captured_cents"] == 0
    assert roi["time_saved"]["hours_change_pct"] is None      # no prior baseline
