"""
Phase 10 — Enterprise administration: cross-location benchmarking + audit center.

Benchmarking must rank sites within an organization by revenue and roll up chain
totals; the audit center must aggregate governance entries across all sites. Both
must be strictly tenant-scoped — one tenant can never read another's organization.
"""

from datetime import timedelta

import pytest

import models
import auth
from time_utils import utcnow
from ai.enterprise import benchmark_organization, org_audit_center


def _org_with_sites(db, tenant_id, org_name="Chain"):
    org = models.Organization(tenant_id=tenant_id, name=org_name)
    db.add(org)
    db.commit()
    return org


def _site(db, tenant_id, org_id, name, revenue_each, orders):
    r = models.Restaurant(tenant_id=tenant_id, name=name, address="x", organization_id=org_id)
    db.add(r)
    db.commit()
    for i in range(orders):
        db.add(models.Order(restaurant_id=r.id, status=models.OrderStatus.SERVED,
                            payment_method=models.PaymentMethod.CASH, is_paid=True,
                            total=revenue_each, created_at=utcnow() - timedelta(days=i % 20)))
    db.commit()
    return r


@pytest.fixture
def chain(db_session):
    tenant = models.Tenant(name="ChainCo")
    db_session.add(tenant)
    db_session.commit()
    org = _org_with_sites(db_session, tenant.id)
    _site(db_session, tenant.id, org.id, "Westlands", 5000, 20)   # bigger
    _site(db_session, tenant.id, org.id, "CBD", 1000, 10)         # smaller
    return db_session, tenant, org


def test_benchmark_ranks_sites_by_revenue(chain):
    db, _tenant, org = chain
    out = benchmark_organization(db, org.id)
    assert out["available"] is True
    assert out["site_count"] == 2
    assert out["sites"][0]["name"] == "Westlands"    # ranked first
    assert out["sites"][0]["rank"] == 1
    assert out["leaders"]["top_revenue"] == "Westlands"
    assert out["leaders"]["bottom_revenue"] == "CBD"
    assert out["totals"]["revenue_30d_cents"] == (5000 * 20 + 1000 * 10)


def test_benchmark_unknown_org_degrades(db_session):
    out = benchmark_organization(db_session, 999)
    assert out["available"] is False


def test_audit_center_aggregates_across_sites(chain):
    db, _tenant, org = chain
    sites = db.query(models.Restaurant).filter_by(organization_id=org.id).all()
    from ai.evaluation.tracker import write_audit_log
    for s in sites:
        write_audit_log(db, s.id, "price_changed", "pricing_intelligence",
                        reasoning="test", approved_by="owner")
    out = org_audit_center(db, org.id, days=30)
    assert out["available"] is True
    assert out["total_actions"] == 2
    assert out["by_action_type"]["price_changed"] == 2
    assert len(out["by_site"]) == 2


# ── HTTP + tenant isolation ─────────────────────────────────────────────────────

def _admin(db, tenant_name, email):
    tenant = models.Tenant(name=tenant_name)
    db.add(tenant)
    db.commit()
    user = models.User(tenant_id=tenant.id, email=email,
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    db.add(user)
    db.commit()
    return tenant, {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}


def test_benchmark_route_is_tenant_scoped(client, db_session):
    # tenant A owns the org; tenant B must not be able to read it
    tenant_a, headers_a = _admin(db_session, "A", "a@e.com")
    org = _org_with_sites(db_session, tenant_a.id)
    _site(db_session, tenant_a.id, org.id, "A-Site", 2000, 5)

    _tenant_b, headers_b = _admin(db_session, "B", "b@e.com")

    ok = client.get(f"/api/v1/enterprise/benchmark?organization_id={org.id}", headers=headers_a)
    assert ok.status_code == 200 and ok.json()["available"] is True

    denied = client.get(f"/api/v1/enterprise/benchmark?organization_id={org.id}", headers=headers_b)
    assert denied.status_code == 200
    assert denied.json()["available"] is False       # B cannot see A's org
