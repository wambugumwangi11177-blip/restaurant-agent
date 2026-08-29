"""
TOTP multi-factor auth (Phase 5, 2026-07-12).

Covers the pure-stdlib TOTP primitives and the full enroll -> enable -> login
flow over HTTP, including that login now requires a valid code once enabled.
"""

import base64
import struct
import time

import auth


def _current_code(secret_b32: str) -> str:
    """Compute the code the same way an authenticator app would (independent of
    auth._hotp so this is a real cross-check, not a tautology)."""
    key = base64.b32decode(secret_b32, casefold=True)
    import hashlib, hmac
    counter = int(time.time() // 30)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    binary = ((mac[o] & 0x7F) << 24 | mac[o + 1] << 16 | mac[o + 2] << 8 | mac[o + 3])
    return str(binary % 1_000_000).zfill(6)


def test_totp_roundtrip_and_rejects_wrong_code():
    secret = auth.generate_mfa_secret()
    assert auth.verify_totp(secret, _current_code(secret)) is True
    assert auth.verify_totp(secret, "000000") is False
    assert auth.verify_totp(secret, "abc") is False
    assert auth.verify_totp(secret, "") is False


def _register(client, email="mfa@e.com"):
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": "GoodPass1", "tenant_name": "T"})
    assert r.status_code == 201
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
    # ...and with the right code accepted.
    ok = client.post("/api/v1/auth/login",
                     json={"email": "mfa@e.com", "password": "GoodPass1", "mfa_code": _current_code(secret)})
    assert ok.status_code == 200 and "access_token" in ok.json()


def test_disable_requires_valid_code(client, db_session):
    token = _register(client, "mfa2@e.com")
    hdr = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=hdr).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=hdr, json={"code": _current_code(secret)})

    assert client.post("/api/v1/auth/mfa/disable", headers=hdr, json={"code": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/mfa/disable", headers=hdr, json={"code": _current_code(secret)}).status_code == 200
    # After disable, login without a code works again.
    assert client.post("/api/v1/auth/login",
                       json={"email": "mfa2@e.com", "password": "GoodPass1"}).status_code == 200
