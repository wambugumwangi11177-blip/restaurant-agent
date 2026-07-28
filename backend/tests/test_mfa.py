"""
TOTP multi-factor auth (Phase 5, 2026-07-12).

Covers the pure-stdlib TOTP primitives and the full enroll -> enable -> login
flow over HTTP, including that login now requires a valid code once enabled.
"""

import base64
import struct
import time

import auth


def _code_for_step(secret_b32: str, step: int) -> str:
    """Compute the code for an explicit 30s step, the same way an authenticator
    app would (independent of auth._hotp so this is a real cross-check, not a
    tautology)."""
    key = base64.b32decode(secret_b32, casefold=True)
    import hashlib, hmac
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    binary = ((mac[o] & 0x7F) << 24 | mac[o + 1] << 16 | mac[o + 2] << 8 | mac[o + 3])
    return str(binary % 1_000_000).zfill(6)


def _now_step() -> int:
    return int(time.time() // 30)


def _current_code(secret_b32: str) -> str:
    return _code_for_step(secret_b32, _now_step())


def _next_code(secret_b32: str) -> str:
    """The NEXT step's code — still inside verify_totp's +/-1 skew window, but a
    different step, so it isn't refused as a replay of an already-spent code.
    Codes are single-use now (RFC 6238 §5.2), so a flow that authenticates twice
    in a row has to move to a fresh step exactly like a real user waiting for
    their app to roll over."""
    return _code_for_step(secret_b32, _now_step() + 1)


def test_totp_roundtrip_and_rejects_wrong_code():
    secret = auth.generate_mfa_secret()
    assert auth.verify_totp(secret, _current_code(secret)) is True
    assert auth.verify_totp(secret, "000000") is False
    assert auth.verify_totp(secret, "abc") is False
    assert auth.verify_totp(secret, "") is False


def _register(client, email="mfa@e.com"):
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": "GoodPass1", "tenant_name": "T"})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_full_mfa_enrollment_and_login_enforcement(client, db_session):
    token = _register(client)
    hdr = {"Authorization": f"Bearer {token}"}

    # Login works without a code before MFA is enabled.
    assert client.post("/api/v1/auth/login",
                       json={"email": "mfa@e.com", "password": "GoodPass1"}).status_code == 200

    # Setup returns a secret + provisioning URI; MFA not yet active.
    setup = client.post("/api/v1/auth/mfa/setup", headers=hdr)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")

    # Enable requires a valid code.
    assert client.post("/api/v1/auth/mfa/enable", headers=hdr,
                       json={"code": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/mfa/enable", headers=hdr,
                       json={"code": _current_code(secret)}).status_code == 200

    # Now login WITHOUT a code is rejected...
    assert client.post("/api/v1/auth/login",
                       json={"email": "mfa@e.com", "password": "GoodPass1"}).status_code == 401
    # ...with a wrong code rejected...
    assert client.post("/api/v1/auth/login",
                       json={"email": "mfa@e.com", "password": "GoodPass1", "mfa_code": "000000"}).status_code == 401
    # ...and with the right code accepted. Uses the NEXT step's code: /mfa/enable
    # above spent the current one, and codes are single-use.
    ok = client.post("/api/v1/auth/login",
                     json={"email": "mfa@e.com", "password": "GoodPass1", "mfa_code": _next_code(secret)})
    assert ok.status_code == 200 and "access_token" in ok.json()


def test_disable_requires_valid_code(client, db_session):
    token = _register(client, "mfa2@e.com")
    hdr = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=hdr).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=hdr, json={"code": _current_code(secret)})

    assert client.post("/api/v1/auth/mfa/disable", headers=hdr, json={"code": "000000"}).status_code == 400
    # Next step's code — enable() above spent the current one.
    assert client.post("/api/v1/auth/mfa/disable", headers=hdr, json={"code": _next_code(secret)}).status_code == 200
    # After disable, login without a code works again.
    assert client.post("/api/v1/auth/login",
                       json={"email": "mfa2@e.com", "password": "GoodPass1"}).status_code == 200


# ── single-use enforcement (RFC 6238 §5.2) ──────────────────────────────────────
#
# Before this, verify_totp's +/-1-step skew window meant a code captured by an
# attacker (shoulder-surf, phishing proxy, malware on the phone) stayed valid for
# the rest of that ~90-second window — the legitimate user logging in did not
# invalidate it. Each code is now burned once spent.

def test_totp_step_is_replay_helper():
    assert auth.totp_step_is_replay(None, 100) is False      # nothing spent yet
    assert auth.totp_step_is_replay(100, 101) is False       # newer step -> fine
    assert auth.totp_step_is_replay(100, 100) is True        # exact reuse
    assert auth.totp_step_is_replay(100, 99) is True         # older, backward-skew replay


def test_verify_totp_step_returns_the_matching_step():
    secret = auth.generate_mfa_secret()
    step = _now_step()
    assert auth.verify_totp_step(secret, _code_for_step(secret, step)) == step
    assert auth.verify_totp_step(secret, _code_for_step(secret, step + 1)) == step + 1
    assert auth.verify_totp_step(secret, "000000") is None


def test_captured_login_code_cannot_be_replayed(client, db_session):
    """The core fix: a code that already logged someone in is dead, even though
    it is still inside its 90-second validity window."""
    import models
    token = _register(client, "replay@e.com")
    hdr = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=hdr).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=hdr, json={"code": _current_code(secret)})

    code = _next_code(secret)
    body = {"email": "replay@e.com", "password": "GoodPass1", "mfa_code": code}

    first = client.post("/api/v1/auth/login", json=body)
    assert first.status_code == 200, "the legitimate login must succeed"

    # Same code, immediately again — still within its validity window, but spent.
    replay = client.post("/api/v1/auth/login", json=body)
    assert replay.status_code == 401, "a spent TOTP code must not authenticate twice"

    # The spent step was persisted, which is what makes the refusal durable
    # rather than in-memory.
    user = db_session.query(models.User).filter(models.User.email == "replay@e.com").first()
    db_session.refresh(user)
    assert user.mfa_last_used_step is not None


def test_replay_of_an_older_code_is_also_refused(client, db_session):
    """Backward skew: once step N is spent, the previous step's code must not
    work either — otherwise the window is only half closed."""
    token = _register(client, "replay2@e.com")
    hdr = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=hdr).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=hdr, json={"code": _current_code(secret)})

    # Spend the NEXT step, then try the CURRENT (older) one, still in-window.
    assert client.post("/api/v1/auth/login", json={
        "email": "replay2@e.com", "password": "GoodPass1", "mfa_code": _next_code(secret)
    }).status_code == 200

    older = client.post("/api/v1/auth/login", json={
        "email": "replay2@e.com", "password": "GoodPass1", "mfa_code": _current_code(secret)
    })
    assert older.status_code == 401
