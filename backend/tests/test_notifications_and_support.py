"""
routers/notifications.py + routers/support.py — the in-app comms channel
built because Twilio is unfunded. Covers: notification feed scoping (never
another user's rows), push-subscription upsert-by-endpoint idempotency, and
support ticket access control (creator + Owner/Manager triage only, everyone
else 403; a reply reopens a resolved ticket; status changes require
Owner/Manager).
"""

import auth
import models


def _user_with_staff_role(db_session, suffix, role=models.Role.STAFF, staff_role=None, is_active=True):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role,
        staff_role=staff_role,
        is_active=is_active,
        token_version=0,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, user, restaurant


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── /notifications ───────────────────────────────────────────────────────

def test_list_notifications_empty_for_new_user(client, db_session):
    token, _, _ = _user_with_staff_role(db_session, "notif1", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    r = client.get("/notifications/", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["unread_count"] == 0


def test_notifications_are_scoped_to_the_caller_only(client, db_session):
    token_a, user_a, restaurant = _user_with_staff_role(db_session, "notifA", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    token_b, user_b, _ = _user_with_staff_role(db_session, "notifB", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    db_session.add(models.Notification(
        user_id=user_a.id, title="For A", body="body", event_type="test.event",
    ))
    db_session.commit()

    r_a = client.get("/notifications/", headers=_auth(token_a))
    r_b = client.get("/notifications/", headers=_auth(token_b))
    assert len(r_a.json()["items"]) == 1
    assert len(r_b.json()["items"]) == 0


def test_mark_read_and_mark_all_read(client, db_session):
    token, user, _ = _user_with_staff_role(db_session, "notifC", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    n1 = models.Notification(user_id=user.id, title="One", body="b", event_type="test.event")
    n2 = models.Notification(user_id=user.id, title="Two", body="b", event_type="test.event")
    db_session.add_all([n1, n2])
    db_session.commit()
    db_session.refresh(n1)
    db_session.refresh(n2)

    r = client.post(f"/notifications/{n1.id}/read", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["is_read"] is True

    listed = client.get("/notifications/", headers=_auth(token)).json()
    assert listed["unread_count"] == 1

    r_all = client.post("/notifications/read-all", headers=_auth(token))
    assert r_all.json()["marked_read"] == 1

    listed2 = client.get("/notifications/", headers=_auth(token)).json()
    assert listed2["unread_count"] == 0


def test_mark_read_404_for_someone_elses_notification(client, db_session):
    token_a, user_a, _ = _user_with_staff_role(db_session, "notifD", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    token_b, user_b, _ = _user_with_staff_role(db_session, "notifE", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    n1 = models.Notification(user_id=user_a.id, title="One", body="b", event_type="test.event")
    db_session.add(n1)
    db_session.commit()
    db_session.refresh(n1)

    r = client.post(f"/notifications/{n1.id}/read", headers=_auth(token_b))
    assert r.status_code == 404


def test_subscribe_is_idempotent_by_endpoint(client, db_session):
    token, user, _ = _user_with_staff_role(db_session, "notifF", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    body = {"endpoint": "https://push.example/abc", "p256dh": "p1", "auth": "a1"}

    r1 = client.post("/notifications/subscribe", json=body, headers=_auth(token))
    assert r1.status_code == 201

    r2 = client.post("/notifications/subscribe", json=body, headers=_auth(token))
    assert r2.status_code == 201

    rows = db_session.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == "https://push.example/abc"
    ).all()
    assert len(rows) == 1


def test_subscribe_reassigns_endpoint_to_new_user_and_unsubscribe_is_scoped(client, db_session):
    token_a, user_a, _ = _user_with_staff_role(db_session, "notifG", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    token_b, user_b, _ = _user_with_staff_role(db_session, "notifH", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    endpoint = "https://push.example/shared-device"

    client.post("/notifications/subscribe", json={"endpoint": endpoint, "p256dh": "p", "auth": "a"}, headers=_auth(token_a))
    client.post("/notifications/subscribe", json={"endpoint": endpoint, "p256dh": "p2", "auth": "a2"}, headers=_auth(token_b))

    row = db_session.query(models.PushSubscription).filter(models.PushSubscription.endpoint == endpoint).first()
    assert row.user_id == user_b.id

    # user_a can no longer unsubscribe it (it's not theirs anymore).
    r_wrong = client.post("/notifications/unsubscribe", json={"endpoint": endpoint}, headers=_auth(token_a))
    assert r_wrong.json()["unsubscribed"] is False

    r_right = client.post("/notifications/unsubscribe", json={"endpoint": endpoint}, headers=_auth(token_b))
    assert r_right.json()["unsubscribed"] is True


# ── /support ──────────────────────────────────────────────────────────────

def test_create_ticket_notifies_owner(client, db_session):
    token_owner, owner, restaurant = _user_with_staff_role(db_session, "supA", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    tenant = db_session.query(models.Tenant).filter(models.Tenant.id == owner.tenant_id).first()
    waiter = models.User(
        tenant_id=tenant.id, email="waiterA@e.com", hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0,
    )
    db_session.add(waiter)
    db_session.commit()
    token_waiter = auth.create_access_token({"sub": waiter.email, "ver": 0})

    r = client.post(
        "/support/tickets",
        json={"subject": "POS is frozen", "message": "Can't take orders at table 4"},
        headers=_auth(token_waiter),
    )
    assert r.status_code == 201
    ticket = r.json()
    assert ticket["status"] == "open"
    assert ticket["message_count"] == 1

    owner_notifs = db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).all()
    assert len(owner_notifs) == 1
    assert "POS is frozen" in owner_notifs[0].title


def test_staff_sees_only_own_tickets_manager_sees_all(client, db_session):
    tenant = models.Tenant(name="Tsup2")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Rsup2", address="x")
    db_session.add(restaurant)
    waiter = models.User(tenant_id=tenant.id, email="w2@e.com", hashed_password=auth.get_password_hash("x"),
                          role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0)
    kitchen = models.User(tenant_id=tenant.id, email="k2@e.com", hashed_password=auth.get_password_hash("x"),
                           role=models.Role.STAFF, staff_role=models.StaffRole.KITCHEN, token_version=0)
    manager = models.User(tenant_id=tenant.id, email="m2@e.com", hashed_password=auth.get_password_hash("x"),
                           role=models.Role.STAFF, staff_role=models.StaffRole.MANAGER, token_version=0)
    db_session.add_all([waiter, kitchen, manager])
    db_session.commit()
    tok_w = auth.create_access_token({"sub": waiter.email, "ver": 0})
    tok_k = auth.create_access_token({"sub": kitchen.email, "ver": 0})
    tok_m = auth.create_access_token({"sub": manager.email, "ver": 0})

    client.post("/support/tickets", json={"subject": "Waiter issue", "message": "m"}, headers=_auth(tok_w))
    client.post("/support/tickets", json={"subject": "Kitchen issue", "message": "m"}, headers=_auth(tok_k))

    waiter_view = client.get("/support/tickets", headers=_auth(tok_w)).json()
    assert len(waiter_view) == 1
    assert waiter_view[0]["subject"] == "Waiter issue"

    manager_view = client.get("/support/tickets", headers=_auth(tok_m)).json()
    assert len(manager_view) == 2


def test_unrelated_staff_cannot_view_someone_elses_ticket(client, db_session):
    tenant = models.Tenant(name="Tsup3")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Rsup3", address="x")
    db_session.add(restaurant)
    waiter = models.User(tenant_id=tenant.id, email="w3@e.com", hashed_password=auth.get_password_hash("x"),
                          role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0)
    kitchen = models.User(tenant_id=tenant.id, email="k3@e.com", hashed_password=auth.get_password_hash("x"),
                           role=models.Role.STAFF, staff_role=models.StaffRole.KITCHEN, token_version=0)
    db_session.add_all([waiter, kitchen])
    db_session.commit()
    tok_w = auth.create_access_token({"sub": waiter.email, "ver": 0})
    tok_k = auth.create_access_token({"sub": kitchen.email, "ver": 0})

    created = client.post("/support/tickets", json={"subject": "Private", "message": "m"}, headers=_auth(tok_w)).json()

    r = client.get(f"/support/tickets/{created['id']}", headers=_auth(tok_k))
    assert r.status_code == 403


def test_reply_reopens_resolved_ticket_and_notifies_creator(client, db_session):
    token_owner, owner, restaurant = _user_with_staff_role(db_session, "supB", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    tenant = db_session.query(models.Tenant).filter(models.Tenant.id == owner.tenant_id).first()
    waiter = models.User(tenant_id=tenant.id, email="w4@e.com", hashed_password=auth.get_password_hash("x"),
                          role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0)
    db_session.add(waiter)
    db_session.commit()
    tok_w = auth.create_access_token({"sub": waiter.email, "ver": 0})

    created = client.post("/support/tickets", json={"subject": "Fridge broken", "message": "m"}, headers=_auth(tok_w)).json()
    tid = created["id"]

    client.patch(f"/support/tickets/{tid}/status", json={"status": "resolved"}, headers=_auth(token_owner))
    resolved = client.get(f"/support/tickets/{tid}", headers=_auth(tok_w)).json()
    assert resolved["status"] == "resolved"

    reply = client.post(f"/support/tickets/{tid}/messages", json={"body": "Still broken!"}, headers=_auth(tok_w))
    assert reply.status_code == 200
    assert reply.json()["status"] == "in_progress"
    assert len(reply.json()["messages"]) == 2

    owner_notifs = db_session.query(models.Notification).filter(
        models.Notification.user_id == owner.id, models.Notification.event_type == "support.ticket_reply"
    ).all()
    assert len(owner_notifs) == 1


def test_update_status_requires_owner_or_manager(client, db_session):
    tenant = models.Tenant(name="Tsup4")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Rsup4", address="x")
    db_session.add(restaurant)
    waiter = models.User(tenant_id=tenant.id, email="w5@e.com", hashed_password=auth.get_password_hash("x"),
                          role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0)
    db_session.add(waiter)
    db_session.commit()
    tok_w = auth.create_access_token({"sub": waiter.email, "ver": 0})

    created = client.post("/support/tickets", json={"subject": "X", "message": "m"}, headers=_auth(tok_w)).json()
    r = client.patch(f"/support/tickets/{created['id']}/status", json={"status": "resolved"}, headers=_auth(tok_w))
    assert r.status_code == 403


def test_update_status_rejects_unknown_status(client, db_session):
    token_owner, owner, restaurant = _user_with_staff_role(db_session, "supC", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    created = client.post("/support/tickets", json={"subject": "X", "message": "m"}, headers=_auth(token_owner)).json()
    r = client.patch(f"/support/tickets/{created['id']}/status", json={"status": "not_a_real_status"}, headers=_auth(token_owner))
    assert r.status_code == 400
