"""
app/security.py
───────────────
Password hashing (Argon2id), password policy, JWT issue/verify with
`token_version` revocation, and RFC 6238 TOTP for MFA.
Ported from restaurant-agent/backend/auth.py (ADR 0002/0003 there), with
PyJWT in place of python-jose.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings

_ph = PasswordHasher()  # argon2-cffi defaults are Argon2id with OWASP-grade params

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


class WeakPasswordError(ValueError):
    pass


def require_strong_password(password: str) -> None:
    problems = []
    if len(password) < 12:
        problems.append("at least 12 characters")
    if not any(c.islower() for c in password):
        problems.append("a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    if problems:
        raise WeakPasswordError("Password needs " + ", ".join(problems))


def create_access_token(user_id: int, workspace_id: int, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "wid": workspace_id,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on any invalid/expired token."""
    return jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "wid", "ver", "exp"]},
    )


# ── TOTP (RFC 6238, SHA-1, 30s, 6 digits — what authenticator apps expect) ──

def generate_mfa_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(key: bytes, counter: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def _b32decode(secret_b32: str) -> bytes:
    padded = secret_b32.upper() + "=" * (-len(secret_b32) % 8)
    return base64.b32decode(padded)


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(_b32decode(secret_b32), int((at or time.time()) // 30))


def verify_totp(secret_b32: str, code: str, window: int = 1, at: float | None = None) -> bool:
    if not code or not code.isdigit() or len(code) != 6:
        return False
    key = _b32decode(secret_b32)
    counter = int((at or time.time()) // 30)
    return any(
        hmac.compare_digest(_hotp(key, counter + drift), code)
        for drift in range(-window, window + 1)
    )


def mfa_provisioning_uri(email: str, secret_b32: str, issuer: str = "CompanyOS") -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}"
        f"?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
