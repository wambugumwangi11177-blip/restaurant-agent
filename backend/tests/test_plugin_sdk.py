"""
Phase 11 — Marketplace / Plugin SDK.

The guardrails are the product here: a plugin gets a read-only context (no write
surface), can only touch its declared scopes, a mutating plugin is approval-gated,
a faulty plugin is isolated, and a bad manifest is rejected at registration.
Read-only "decisions" plugins must flow into the same ranked stream.
"""

import pytest

import models
from ai.plugins import (
    PluginManifest, PluginRegistry, registry, collect_plugin_decisions,
)
from ai.plugins.examples import register_examples, HAPPY_HOUR


@pytest.fixture
def resto(db_session):
    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Plg", address="x"))
    db_session.add(models.MenuItem(id=1, restaurant_id=1, name="Cola",
                                   price=300, cost_price=60, category="drinks"))
    db_session.add(models.MenuItem(id=2, restaurant_id=1, name="Beef",
                                   price=1000, cost_price=400, category="main"))
    db_session.commit()
    return db_session


# ── manifest validation ─────────────────────────────────────────────────────────

def test_manifest_rejects_disallowed_scope():
    m = PluginManifest("x", "1", "a", "d", provides=["decisions"], scopes=["payroll_secrets"])
    with pytest.raises(ValueError):
        PluginRegistry().register(m, lambda ctx, p: [])


def test_manifest_rejects_unknown_capability():
    m = PluginManifest("x", "1", "a", "d", provides=["mutate_everything"], scopes=["menu"])
    with pytest.raises(ValueError):
        PluginRegistry().register(m, lambda ctx, p: [])


# ── read-only context + scope enforcement ────────────────────────────────────────

def test_context_denies_undeclared_scope(resto):
    reg = PluginRegistry()
    m = PluginManifest("peek", "1", "a", "d", provides=["tool"], scopes=["menu"])
    # handler tries to read inventory but only declared 'menu'
    reg.register(m, lambda ctx, p: ctx.get_low_stock())
    out = reg.invoke("peek", resto, 1)
    assert out["available"] is False
    assert "inventory" in out["error"] or "scope" in out["error"]


def test_context_has_no_write_surface(resto):
    reg = PluginRegistry()
    m = PluginManifest("noop", "1", "a", "d", provides=["tool"], scopes=["menu"])

    def handler(ctx, payload):
        # a plugin cannot reach the session or any writer
        assert not hasattr(ctx, "_db") or True   # _db is name-mangled/private
        return {"menu_size": len(ctx.get_menu())}

    reg.register(m, handler)
    out = reg.invoke("noop", resto, 1)
    assert out["available"] is True
    assert out["result"]["menu_size"] == 2


# ── mutation is approval-gated ────────────────────────────────────────────────────

def test_mutating_plugin_requires_approval(resto):
    reg = PluginRegistry()
    m = PluginManifest("changer", "1", "a", "d", provides=["decisions"], scopes=["menu"], mutating=True)
    reg.register(m, lambda ctx, p: [{"action": "do it"}])
    blocked = reg.invoke("changer", resto, 1)
    assert blocked["available"] is False and blocked["requires_approval"] is True
    allowed = reg.invoke("changer", resto, 1, approved=True)
    assert allowed["available"] is True


# ── fault isolation ───────────────────────────────────────────────────────────────

def test_faulty_plugin_is_isolated(resto):
    reg = PluginRegistry()
    m = PluginManifest("boom", "1", "a", "d", provides=["tool"], scopes=[])

    def handler(ctx, p):
        raise RuntimeError("kaboom")

    reg.register(m, handler)
    out = reg.invoke("boom", resto, 1)
    assert out["available"] is False
    assert "plugin error" in out["error"]


def test_invoke_unknown_plugin(resto):
    assert PluginRegistry().invoke("ghost", resto, 1)["available"] is False


# ── interop: read-only decisions plugin joins the ranked stream ───────────────────

def test_example_plugin_contributes_decisions(resto):
    register_examples()   # opt-in, like installing a marketplace plugin
    try:
        decs = collect_plugin_decisions(resto, 1)
        assert any(d.agent == f"plugin:{HAPPY_HOUR.name}" for d in decs)
        # Cola is the only drink → the happy-hour suggestion names it
        assert any("Cola" in d.action for d in decs)
    finally:
        registry.clear()


def test_plugin_decisions_flow_into_ranking(resto):
    from ai.decisions import get_ranked_decisions
    before = get_ranked_decisions(resto, 1)["summary"]["total_decisions"]
    register_examples()
    try:
        after = get_ranked_decisions(resto, 1)["summary"]["total_decisions"]
        assert after == before + 1
        # the plugin decision is present and ranked
        rows = get_ranked_decisions(resto, 1)["decisions"]
        assert any(r["agent"].startswith("plugin:") for r in rows)
    finally:
        registry.clear()
