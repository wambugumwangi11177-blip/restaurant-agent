"""
S4.5 — "Based on: your floor 40% · Change": the sheet that opens on a number's rule shows, as the owner moves the slider, how many of
Home's cards would change (docs/v2/SPEC.md §3.2). The answer comes from the real engines under the proposed setting and is rolled back:
nothing is saved, nothing is audited, and what the preview says is exactly what saving does.

Home also says whether the owner has chosen their targets and how old the restaurant is (`setup`), for the first-run questions and the
guided first week.
"""
from datetime import timedelta

import pytest

import auth
import models
from tests.fixtures import golden_restaurant as gr
from time_utils import eat_date, utcnow

API = "/api/v1/owner"


def _h(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': 0})}"}


def _preview(client, g, **changes):
    return client.post(f"{API}/settings/preview", json=changes, headers=_h(g.owner))


def _ranked(client, g):
    return {c["id"]: c for c in client.get(f"{API}/home", headers=_h(g.owner)).json()["costing_you_money"]["ranked"]}


@pytest.fixture
def rich(db_session):
    g = gr.build_skeleton(db_session)
    gr.seed_chicken_reprice(db_session, g)             # Quarter chicken keeps 35%, under the 40% floor
    gr.seed_burger_delivery(db_session, g)             # a Glovo burger
    gr.seed_chips_below_menu(db_session, g)
    return g


def _settings_rows(db_session):
    return db_session.query(models.RestaurantSettings).count(), db_session.query(models.RestaurantSettingsAudit).count()


# ── what it says ─────────────────────────────────────────────────────────────

def test_lowering_the_floor_makes_the_margin_idea_go_away(client, rich, db_session):
    now = _ranked(client, rich)
    chicken = next(c for c in now.values() if "Quarter chicken" in c["sentence"] and "Glovo" not in c["sentence"] and "Uber" not in c["sentence"] and "Bolt" not in c["sentence"])
    res = _preview(client, rich, margin_floor_pct=30)
    assert res.status_code == 200
    body = res.json()
    assert body["changes"] == [{"key": "margin_floor_pct", "label": "Lowest share you keep on a dish", "unit": "%", "from": 40.0, "to": 30.0}]
    assert chicken["sentence"] in body["disappear"]                                   # at a 30% floor a dish that keeps 35% is fine
    assert body["cards_now"] == len(now) and body["cards_after"] == body["cards_now"] - len(body["disappear"]) + len(body["appear"])
    assert body["changed"] == len(body["appear"]) + len(body["disappear"]) + len(body["figures"]) >= 1


def test_a_commission_change_changes_the_figure_of_a_delivery_card_not_its_existence(client, rich):
    body = _preview(client, rich, commission_glovo_pct=30).json()
    assert any("Burger on Glovo" in s for s in body["figures"])
    assert not any("Burger on Glovo" in s for s in body["appear"] + body["disappear"])


def test_a_value_the_owner_already_has_changes_nothing(client, rich):
    body = _preview(client, rich, margin_floor_pct=40).json()
    assert (body["changes"], body["changed"], body["appear"], body["disappear"], body["figures"]) == ([], 0, [], [], [])
    assert body["cards_now"] == body["cards_after"]


def test_what_the_preview_says_is_exactly_what_saving_does(client, rich):
    before = _ranked(client, rich)
    preview = _preview(client, rich, margin_floor_pct=30, commission_glovo_pct=30).json()
    assert client.put(f"{API}/settings", json={"margin_floor_pct": 30, "commission_glovo_pct": 30}, headers=_h(rich.owner)).status_code == 200
    after = _ranked(client, rich)
    assert len(after) == preview["cards_after"]
    was, now = {c["sentence"] for c in before.values()}, {c["sentence"] for c in after.values()}
    appear, disappear, figures = set(preview["appear"]), set(preview["disappear"]), set(preview["figures"])
    assert appear <= now - was and disappear <= was - now                                  # what appears is new; what goes away is gone
    # a card that comes back with a new price in its words (a Glovo price rise) is one card with a new figure, not one gone and one new
    renamed_now, renamed_was = (now - was) - appear, (was - now) - disappear
    assert len(renamed_now) == len(renamed_was) and renamed_now <= figures
    moved = {a["sentence"] for k, a in after.items() if k in before and a["kes_month"] != before[k]["kes_month"]}
    assert figures == renamed_now | moved
    assert preview["changed"] == len(appear) + len(disappear) + len(figures)


# ── nothing is saved ─────────────────────────────────────────────────────────

def test_a_preview_saves_nothing_audits_nothing_and_leaves_a_new_restaurant_unchosen(client, db_session):
    g = gr.build_skeleton(db_session)
    assert _settings_rows(db_session) == (0, 0)
    assert _preview(client, g, margin_floor_pct=30, cash_tolerance_kes=500).status_code == 200
    assert _settings_rows(db_session) == (0, 0)
    assert client.get(f"{API}/settings", headers=_h(g.owner)).json()["chosen"] is False


def test_a_preview_leaves_existing_settings_exactly_as_they_were(client, rich, db_session):
    client.put(f"{API}/settings", json={"margin_floor_pct": 45}, headers=_h(rich.owner))
    saved = client.get(f"{API}/settings", headers=_h(rich.owner)).json()
    audits = db_session.query(models.RestaurantSettingsAudit).count()
    for _ in range(2):                                                                    # again: a preview does not leave anything behind to differ
        assert _preview(client, rich, margin_floor_pct=20).status_code == 200
    assert client.get(f"{API}/settings", headers=_h(rich.owner)).json() == saved
    assert db_session.query(models.RestaurantSettingsAudit).count() == audits


def test_the_same_preview_twice_gives_the_same_answer(client, rich):
    assert _preview(client, rich, margin_floor_pct=30).json() == _preview(client, rich, margin_floor_pct=30).json()


# ── bounds, roles, tenants ───────────────────────────────────────────────────

@pytest.mark.parametrize("changes", [{"margin_floor_pct": 5}, {"margin_floor_pct": 99}, {"nonsense": 1}, {"margin_floor_pct": "a lot"}, {}])
def test_a_preview_is_bound_by_the_same_rules_as_a_save(client, rich, changes):
    assert _preview(client, rich, **changes).status_code == 422


def test_a_floor_above_the_target_is_refused_in_a_preview_too(client, rich):
    res = _preview(client, rich, margin_floor_pct=60)                                      # the target is 55
    assert res.status_code == 422 and res.json()["detail"]["field"] == "margin_floor_pct"


@pytest.mark.parametrize("role,status", [(models.StaffRole.MANAGER, 403), (models.StaffRole.CONTROLLER, 403), (models.StaffRole.WAITER, 403)])
def test_only_the_owner_may_preview(client, db_session, role, status):
    t = models.Tenant(name=f"T{role.value}")
    db_session.add(t)
    db_session.flush()
    db_session.add(models.Restaurant(tenant_id=t.id, name="R", address="x"))
    u = models.User(tenant_id=t.id, email=f"{role.value}@x.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF, staff_role=role, token_version=0)
    db_session.add(u)
    db_session.commit()
    assert client.post(f"{API}/settings/preview", json={"margin_floor_pct": 30}, headers=_h(u)).status_code == status


def test_anonymous_is_401_and_another_tenants_settings_are_untouched(client, rich, db_session):
    assert client.post(f"{API}/settings/preview", json={"margin_floor_pct": 30}).status_code == 401
    t = models.Tenant(name="Other")
    db_session.add(t)
    db_session.flush()
    r = models.Restaurant(tenant_id=t.id, name="Other", address="x")
    db_session.add(r)
    u = models.User(tenant_id=t.id, email="o@x.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF, staff_role=models.StaffRole.OWNER, token_version=0)
    db_session.add(u)
    db_session.commit()
    client.put(f"{API}/settings", json={"margin_floor_pct": 50}, headers=_h(u))
    body = client.post(f"{API}/settings/preview", json={"margin_floor_pct": 30}, headers=_h(u)).json()
    assert body["cards_now"] == body["cards_after"] == 0                                    # their restaurant has no sales: the owner's cards are not theirs
    assert client.get(f"{API}/settings", headers=_h(u)).json()["fields"][2]["value"] == 50.0


# ── setup: has the owner chosen, and how new is this restaurant ──────────────

def test_home_says_whether_targets_are_chosen_and_how_many_days_old_the_restaurant_is(client, db_session):
    g = gr.build_skeleton(db_session)
    setup = client.get(f"{API}/home", headers=_h(g.owner)).json()["setup"]
    assert setup == {"targets_chosen": False, "age_days": 0}
    client.put(f"{API}/settings", json={"food_cost_target_pct": 35}, headers=_h(g.owner))
    assert client.get(f"{API}/home", headers=_h(g.owner)).json()["setup"]["targets_chosen"] is True


def test_the_age_is_nairobi_days_since_the_tenant_was_created(client, db_session):
    g = gr.build_skeleton(db_session)
    tenant = db_session.get(models.Tenant, g.owner.tenant_id)
    tenant.created_at = utcnow() - timedelta(days=10, hours=1)
    db_session.commit()
    assert client.get(f"{API}/home", headers=_h(g.owner)).json()["setup"]["age_days"] == 10


def test_a_restaurant_that_arrives_with_a_history_is_not_new(client, db_session):
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)                                                       # sales from the days before today; the tenant was created just now
    age = client.get(f"{API}/home", headers=_h(g.owner)).json()["setup"]["age_days"]
    first = db_session.query(models.Order.created_at).filter_by(restaurant_id=g.rid).order_by(models.Order.created_at).first()[0]
    assert age == (eat_date(utcnow()) - eat_date(first)).days >= 5                         # old enough that the guided first week never starts
