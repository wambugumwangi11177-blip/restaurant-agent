"""
REPRICE exists to lift a below-floor item back to the margin floor. Nearest-50
rounding could land just under the exact target (cost 610 → 610/0.6 = 1016.67 →
nearest-50 = 1000 → 39%, under the 40% floor), so REPRICE would recommend a price
that still violates the floor it is restoring. Ceiling to 50 guarantees the
result is at/above the floor. SURGE/STIMULATE already gate post-round; this pins
REPRICE to the same guarantee.
"""
from ai.pricing.analysis import _round_price_up, MIN_MARGIN_PCT


def _margin_pct(price: int, cost: int) -> float:
    return (price - cost) / price * 100


def test_reprice_target_never_falls_below_floor():
    for cost in range(100, 5000, 7):
        exact = cost / (1 - MIN_MARGIN_PCT / 100)
        price = _round_price_up(exact)
        assert _margin_pct(price, cost) >= MIN_MARGIN_PCT - 1e-9, (
            f"cost={cost} price={price} margin={_margin_pct(price, cost):.2f} below floor"
        )


def test_known_regression_case_cost_610():
    # The worked example from the review: nearest-50 gave 1000 (39%).
    price = _round_price_up(610 / (1 - MIN_MARGIN_PCT / 100))
    assert price == 1050
    assert _margin_pct(price, 610) >= MIN_MARGIN_PCT


def test_rounds_to_a_multiple_of_50():
    for cost in (333, 610, 1201, 2500):
        assert _round_price_up(cost / (1 - MIN_MARGIN_PCT / 100)) % 50 == 0
