"""
backend/tests/test_notification_preferences.py
────────────────────────────────────────────────
Muting exists because the feed now records routine activity — every order,
status change and payment — so a busy site writes hundreds of rows a day and the
bell stops being readable without a volume control.

The two properties that make muting safe rather than dangerous:

  • **It hides, it does not suppress.** The row is still written and still
    reaches everyone who has not muted it, so one person's preference can never
    silence an alert for the restaurant.
  • **Some things cannot be muted at all.** "About to run out" and "out of
    stock" mean you are about to stop being able to serve food. Being able to
    switch those off permanently is not a preference, it is a way to lose a
    service.
"""

import pytest

import models
import notifications


@pytest.fixture
def admin(client):
    resp = client.post("/api/v1/auth/register", json={
        "email": "owner@example.com", "password": "GoodPass1", "tenant_name": "Mute Kitchen",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _user(db):
    return db.query(models.User).filter(models.User.email == "owner@example.com").first()


def _restaurant(db):
    return db.query(models.Restaurant).first()


def _seed(db, *categories):
    for c in categories:
        notifications.record(db, _restaurant(db).id, f"{c} happened", category=c,
                             audience=notifications.AUDIENCE_ALL)


# ── the catalogue is the contract with the UI ────────────────────────────────

def test_every_emitted_category_is_in_the_catalogue():
    """
    A category the code emits but the catalogue omits would be invisible on the
    settings screen — unmutable in practice, with no way for a user to find out
    why. Greps the source rather than trusting a hand-kept list.
    """
    import ast
    import pathlib

    # AST, not grep: `category=` is also a keyword on AI Decision adapters
    # (`category="pricing"`), which are a different concept entirely. Only
    # arguments to the notification writers count.
    WRITERS = {"record", "deliver"}
    root = pathlib.Path(__file__).resolve().parent.parent
    emitted = set()

    for path in root.rglob("*.py"):
        if ".venv" in path.parts or path.name.startswith("test_"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in WRITERS:
                continue
            for kw in node.keywords:
                if kw.arg == "category" and isinstance(kw.value, ast.Constant):
                    emitted.add(kw.value.value)

    assert emitted, "found no notification writes at all — the scan is broken"
    missing = emitted - set(notifications.CATEGORY_CATALOGUE)
    assert not missing, f"emitted but not in CATEGORY_CATALOGUE: {sorted(missing)}"


def test_the_two_stockout_categories_cannot_be_muted():
    assert notifications.UNMUTABLE_CATEGORIES == {"stock_critical", "stock_depleted"}


# ── muting filters the feed and the badge ────────────────────────────────────

def test_muting_hides_a_category_from_the_feed(client, db_session, admin):
    _seed(db_session, "order_created", "order_paid")
    user = _user(db_session)

    notifications.set_mutes(db_session, user.id, ["order_created"])

    feed = notifications.list_for(db_session, _restaurant(db_session).id, user_id=user.id)
    assert [n.category for n in feed] == ["order_paid"]


def test_muting_also_drops_the_badge_count(client, db_session, admin):
    """A "3" that opens onto an empty panel is worse than no muting at all."""
    _seed(db_session, "order_created", "order_created", "order_paid")
    user = _user(db_session)
    restaurant = _restaurant(db_session)
    assert notifications.unread_count(db_session, restaurant.id, user_id=user.id) == 3

    notifications.set_mutes(db_session, user.id, ["order_created"])

    assert notifications.unread_count(db_session, restaurant.id, user_id=user.id) == 1


def test_muting_hides_but_never_suppresses(client, db_session, admin):
    """
    The row is still written and still reaches anyone who has not muted it —
    otherwise one person's preference would silence an alert restaurant-wide.
    """
    user = _user(db_session)
    notifications.set_mutes(db_session, user.id, ["order_created"])

    _seed(db_session, "order_created")

    restaurant = _restaurant(db_session)
    assert notifications.list_for(db_session, restaurant.id, user_id=user.id) == []
    # Unfiltered (another user, or the system) still sees it.
    assert len(notifications.list_for(db_session, restaurant.id)) == 1


def test_a_mute_row_on_an_unmutable_category_is_ignored(db_session, client, admin):
    """
    Defends against reclassification: if a category later becomes unmutable, a
    row written while it was still allowed must not keep hiding stockouts.
    """
    user = _user(db_session)
    db_session.add(models.NotificationMute(user_id=user.id, category="stock_critical"))
    db_session.commit()

    _seed(db_session, "stock_critical")

    assert notifications.muted_categories(db_session, user.id) == set()
    assert len(notifications.list_for(db_session, _restaurant(db_session).id, user_id=user.id)) == 1


# ── set_mutes semantics ──────────────────────────────────────────────────────

def test_set_mutes_replaces_rather_than_accumulates(db_session, client, admin):
    user = _user(db_session)

    notifications.set_mutes(db_session, user.id, ["order_created", "order_paid"])
    notifications.set_mutes(db_session, user.id, ["order_paid"])

    assert notifications.muted_categories(db_session, user.id) == {"order_paid"}


def test_set_mutes_is_idempotent_and_makes_no_duplicate_rows(db_session, client, admin):
    user = _user(db_session)

    notifications.set_mutes(db_session, user.id, ["order_created"])
    notifications.set_mutes(db_session, user.id, ["order_created"])

    rows = db_session.query(models.NotificationMute).filter(
        models.NotificationMute.user_id == user.id).count()
    assert rows == 1


def test_unknown_and_unmutable_categories_are_dropped_not_stored(db_session, client, admin):
    user = _user(db_session)

    result = notifications.set_mutes(
        db_session, user.id, ["order_created", "stock_critical", "not_a_real_category"])

    assert result == {"order_created"}
    assert notifications.muted_categories(db_session, user.id) == {"order_created"}


def test_mutes_are_per_user_not_per_restaurant(db_session, client, admin):
    """A head chef muting price changes must not mute them for the owner."""
    import auth as auth_mod

    owner = _user(db_session)
    other = models.User(email="chef@example.com",
                        hashed_password=auth_mod.get_password_hash("GoodPass1"),
                        role=models.Role.STAFF, tenant_id=owner.tenant_id)
    db_session.add(other)
    db_session.commit()

    notifications.set_mutes(db_session, other.id, ["order_created"])
    _seed(db_session, "order_created")

    restaurant = _restaurant(db_session)
    assert notifications.list_for(db_session, restaurant.id, user_id=other.id) == []
    assert len(notifications.list_for(db_session, restaurant.id, user_id=owner.id)) == 1


# ── mark-read semantics under muting ─────────────────────────────────────────

def test_mark_all_read_leaves_muted_entries_alone(db_session, client, admin):
    """
    Silently acknowledging entries you chose not to see would hide them from
    your own future un-muting.
    """
    _seed(db_session, "order_created", "order_paid")
    user = _user(db_session)
    notifications.set_mutes(db_session, user.id, ["order_created"])

    cleared = notifications.mark_all_read(db_session, _restaurant(db_session).id, user_id=user.id)

    assert cleared == 1
    # Un-mute and the hidden one is still waiting, unread.
    notifications.set_mutes(db_session, user.id, [])
    assert notifications.unread_count(db_session, _restaurant(db_session).id, user_id=user.id) == 1


def test_a_muted_notification_can_still_be_marked_read_directly(db_session, client, admin):
    """Muted means hidden from the list, not forbidden — a deep link or a stale
    open tab can still legitimately acknowledge one."""
    _seed(db_session, "order_created")
    user = _user(db_session)
    note = notifications.list_for(db_session, _restaurant(db_session).id)[0]
    notifications.set_mutes(db_session, user.id, ["order_created"])

    assert notifications.mark_read(db_session, _restaurant(db_session).id, note.id,
                                   user_id=user.id) is True


# ── HTTP surface ─────────────────────────────────────────────────────────────

def test_preferences_endpoint_lists_every_category(client, admin):
    body = client.get("/api/v1/notifications/preferences", headers=admin).json()

    by_category = {i["category"]: i for i in body["items"]}
    assert by_category["order_created"]["label"] == "New orders"
    assert by_category["order_created"]["muted"] is False
    assert by_category["stock_critical"]["mutable"] is False


def test_put_preferences_round_trips(client, db_session, admin):
    resp = client.put("/api/v1/notifications/preferences", headers=admin,
                      json={"muted": ["order_created", "order_status"]})

    assert resp.status_code == 200
    muted = {i["category"] for i in resp.json()["items"] if i["muted"]}
    assert muted == {"order_created", "order_status"}

    # And it survives a re-read.
    body = client.get("/api/v1/notifications/preferences", headers=admin).json()
    assert {i["category"] for i in body["items"] if i["muted"]} == {"order_created", "order_status"}


def test_put_preferences_tolerates_a_stale_category(client, admin):
    """
    A 4xx over one unknown name would lose every other choice the user just
    made, so unacceptable entries are dropped and reflected back unmuted.
    """
    resp = client.put("/api/v1/notifications/preferences", headers=admin,
                      json={"muted": ["order_created", "category_from_a_previous_release"]})

    assert resp.status_code == 200
    assert {i["category"] for i in resp.json()["items"] if i["muted"]} == {"order_created"}


def test_muting_over_http_changes_the_feed_and_badge(client, db_session, admin):
    _seed(db_session, "order_created", "order_paid")

    client.put("/api/v1/notifications/preferences", headers=admin,
               json={"muted": ["order_created"]})
    body = client.get("/api/v1/notifications/", headers=admin).json()

    assert [i["category"] for i in body["items"]] == ["order_paid"]
    assert body["unread"] == 1


def test_staff_are_not_offered_switches_they_can_never_receive(client, db_session, admin):
    """A dead switch reads as "you turned this off", which is a different and
    wrong statement."""
    import auth as auth_mod

    owner = _user(db_session)
    staff = models.User(email="staff@example.com",
                        hashed_password=auth_mod.get_password_hash("GoodPass1"),
                        role=models.Role.STAFF, tenant_id=owner.tenant_id)
    db_session.add(staff)
    db_session.commit()

    resp = client.post("/api/v1/auth/login",
                       json={"email": "staff@example.com", "password": "GoodPass1"})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    categories = {i["category"] for i in
                  client.get("/api/v1/notifications/preferences", headers=headers).json()["items"]}

    assert "order_created" in categories          # they receive these
    assert "morning_briefing" not in categories   # they never will
    assert "menu_changed" not in categories


def test_preferences_require_auth(client):
    assert client.get("/api/v1/notifications/preferences").status_code == 401
    assert client.put("/api/v1/notifications/preferences", json={"muted": []}).status_code == 401
