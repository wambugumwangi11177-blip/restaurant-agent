from app.kernel.channels.whatsapp import compute_signature
from app.kernel.models import AuditLog, ChannelMessage

URL = "https://os.example.test/api/v1/webhooks/whatsapp"


def _post(client, params: dict, token: str = "test-twilio-token", signature: str | None = None):
    sig = signature if signature is not None else compute_signature(token, URL, params)
    return client.post("/api/v1/webhooks/whatsapp", data=params, headers={"X-Twilio-Signature": sig})


def _msg(sid: str, body: str, frm: str = "whatsapp:+254712345678") -> dict:
    return {"MessageSid": sid, "From": frm, "To": "whatsapp:+14155238886", "Body": body}


def test_signature_is_required(client, make_workspace):
    make_workspace("acme", phone="0712345678")
    assert _post(client, _msg("SM1", "status"), signature="").status_code == 403
    assert _post(client, _msg("SM1", "status"), token="wrong-token").status_code == 403


def test_known_twilio_signature_vector():
    # Expected values produced by Twilio's official twilio-python 9.11.1
    # RequestValidator.compute_signature on the same inputs (cross-checked
    # 2026-09-26; twilio.com itself was unreachable from the build sandbox).
    params = {"CallSid": "CA1234567890ABCDE", "Caller": "+12349013030", "Digits": "1234",
              "From": "+12349013030", "To": "+18005551212"}
    assert compute_signature("12345", "https://mycompany.com/myapp.php?foo=1&bar=2", params) == "0/KCTR6DLpKmkAf8muzZqo1nDgQ="
    unicode_params = {"MessageSid": "SM1", "From": "whatsapp:+254712345678", "To": "whatsapp:+14155238886",
                      "Body": "ask what's the plan? ünïcode"}
    assert compute_signature("test-twilio-token", URL, unicode_params) \
        == "pi87qM8fBZ/wHaKvN7deoUiZZ54="


def test_member_status_command(client, make_workspace):
    make_workspace("acme", phone="0712345678")
    r = _post(client, _msg("SM1", "Status"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert "Approvals waiting: 0" in r.text


def test_retried_delivery_is_processed_once(client, make_workspace, db):
    make_workspace("acme", phone="0712345678")
    _post(client, _msg("SM-dup", "status"))
    r = _post(client, _msg("SM-dup", "status"))
    assert r.status_code == 200 and "<Message>" not in r.text
    assert db.query(ChannelMessage).filter(ChannelMessage.external_id == "SM-dup").count() == 1


def test_unknown_sender_gets_nothing(client, make_workspace, db):
    make_workspace("acme", phone="0712345678")
    r = _post(client, _msg("SM9", "status", frm="whatsapp:+254799999999"))
    assert r.status_code == 200 and "<Message>" not in r.text
    assert db.query(ChannelMessage).filter(ChannelMessage.external_id == "SM9").one().workspace_id is None


def test_ask_without_llm_returns_sources_and_help_otherwise(client, make_workspace):
    w = make_workspace("acme", phone="0712345678")
    client.post("/api/v1/memory/documents", headers=w["h"], json={"title": "Hours", "content": "Support runs 08:00 to 20:00."})
    r = _post(client, _msg("SM2", "ask when does support run"))
    assert "Hours" in r.text
    assert "Company OS commands" in _post(client, _msg("SM3", "hello")).text


def test_member_without_agent_permission_is_told(client, make_workspace, add_member):
    w = make_workspace("acme")
    add_member(w["h"], "advisor", "adv@acme.example.com", phone="0722000000")
    r = _post(client, _msg("SM4", "status", frm="whatsapp:+254722000000"))
    assert "can't run agents" in r.text


def test_person_export_and_erasure(client, make_workspace, db):
    w = make_workspace("acme")
    p = client.post("/api/v1/records/person", headers=w["h"], json={
        "full_name": "Achieng Otieno", "email": "achieng@example.com", "phone": "0733111222", "notes": "prefers calls"}).json()
    db.add(ChannelMessage(workspace_id=w["ws"].id, channel="whatsapp", direction="out", from_addr="company",
                          to_addr="254733111222", body="Your invoice is ready"))
    db.commit()

    export = client.get(f"/api/v1/privacy/people/{p['id']}/export", headers=w["h"]).json()
    assert export["person"]["email"] == "achieng@example.com"
    assert export["messages"][0]["body"] == "Your invoice is ready"

    assert client.post(f"/api/v1/privacy/people/{p['id']}/erase", headers=w["h"], json={"reason": ""}).status_code == 422
    r = client.post(f"/api/v1/privacy/people/{p['id']}/erase", headers=w["h"], json={"reason": "DSR-2026-001"})
    assert r.status_code == 200
    after = client.get(f"/api/v1/records/person/{p['id']}", headers=w["h"]).json()
    assert (after["full_name"], after["email"], after["phone"], after["notes"]) == (f"Erased person #{p['id']}", None, None, None)
    db.expire_all()
    msg = db.query(ChannelMessage).one()
    assert (msg.body, msg.to_addr) == ("[erased]", "[erased]")
    assert client.patch(f"/api/v1/records/person/{p['id']}", headers=w["h"], json={"notes": "x"}).status_code == 409
    assert client.post(f"/api/v1/privacy/people/{p['id']}/erase", headers=w["h"], json={"reason": "again"}).status_code == 409
    erase_row = db.query(AuditLog).filter(AuditLog.action == "privacy.erase").one()
    assert erase_row.changes == {"reason": "DSR-2026-001", "messages_scrubbed": 1}


def test_privacy_is_founder_only(client, make_workspace, add_member):
    w = make_workspace("acme")
    staff = add_member(w["h"], "staff", "s@acme.example.com")
    p = client.post("/api/v1/records/person", headers=w["h"], json={"full_name": "X"}).json()
    assert client.get(f"/api/v1/privacy/people/{p['id']}/export", headers=staff).status_code == 403


def test_health_ops_events_notifications(client, make_workspace, add_member):
    w = make_workspace("acme")
    assert client.get("/health").json()["status"] == "ok"
    ops = client.get("/api/v1/ops/status", headers=w["h"]).json()
    assert ops["llm_provider"] is None and ops["channels"] == {"whatsapp": False, "email": False}
    staff = add_member(w["h"], "staff", "s@acme.example.com")
    assert client.get("/api/v1/ops/status", headers=staff).status_code == 403

    client.post("/api/v1/records/note", headers=w["h"], json={"title": "n"})
    types = [e["type"] for e in client.get("/api/v1/events", headers=w["h"]).json()]
    assert "record.created" in types and "member.added" in types

    client.post("/api/v1/approvals", headers=staff, json={"tool": "send_whatsapp", "args": {"to": "0712345678", "body": "hi"}})
    notes = client.get("/api/v1/notifications", headers=w["h"], params={"unread_only": True}).json()
    assert len(notes) == 1
    client.post("/api/v1/notifications/read-all", headers=w["h"])
    assert client.get("/api/v1/notifications", headers=w["h"], params={"unread_only": True}).json() == []


def test_request_id_and_body_limit(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    big = client.post("/api/v1/auth/login", content=b"x", headers={"content-length": str(6 * 1024 * 1024)})
    assert big.status_code == 413
