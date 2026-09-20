from observer_mode import canonical_path, is_blocked_request
from integration.source_contract import SourceRegistry, UnconfiguredSource


def test_blocks_real_operational_mutations_on_both_api_surfaces():
    assert is_blocked_request("POST", "/api/v1/orders/")
    assert is_blocked_request("POST", "/stock/transfers")
    assert is_blocked_request("POST", "/api/v1/attendance/clock-in")
    assert is_blocked_request("POST", "/api/v1/ai/pricing/1/approve")
    assert is_blocked_request("POST", "/api/v1/overview/attention/x/decision")
    assert is_blocked_request("GET", "/api/v1/overview/today")
    assert is_blocked_request("GET", "/api/v1/reports/daily")
    assert is_blocked_request("GET", "/api/v1/ai/ask")
    assert not is_blocked_request("GET", "/api/v1/orders/")


def test_support_and_webhooks_are_unavailable_even_on_get():
    assert is_blocked_request("GET", "/api/v1/support/tickets")
    assert is_blocked_request("POST", "/webhooks/mpesa")
    assert canonical_path("/api/v1/reports/daily") == "/reports/daily"


def test_source_registry_never_infers_an_unconfigured_adapter():
    assert isinstance(SourceRegistry().resolve(999), UnconfiguredSource)
