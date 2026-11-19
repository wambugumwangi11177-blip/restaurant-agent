"""Question routing for the owner AI ask box (_route in routers.ai_ask)."""
from __future__ import annotations

import pytest

from routers.ai_ask import _route
from routers.overview import records_directly

import models


@pytest.mark.parametrize("question,expected", [
    ("How can I increase my profit?", "profit"),
    ("Which items make me the most profit?", "profit"),
    ("Who is working today?", "staff"),
    ("How many customers are expected today?", "bookings"),
    ("How often are customers not showing up?", "bookings"),
    ("Which ingredients are at risk of expiring?", "stock"),
    ("What stock moves happened this week?", "stock"),
])
def test_specific_terms_route_to_the_right_module(question: str, expected: str):
    assert _route(question) == expected


def test_delivery_mismatch_question_routes_to_stock_or_ops():
    assert _route("Any delivery photo mismatches I should know about?") in {"stock", "ops"}


def test_an_unmatched_question_falls_back_to_general_operations():
    assert _route("What is the meaning of life?") == "ops"


def test_eleven_tenant_uses_direct_source_records(db_session):
    tenant = models.Tenant(name="Eleven")
    db_session.add(tenant)
    db_session.commit()
    assert records_directly(db_session, tenant.id) is True