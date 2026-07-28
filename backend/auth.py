"""
auth.py — Authentication utilities
Changes vs original:
  - SECRET_KEY now CRASHES at startup if not set (was silently using "your_secret_key_here")
  - Token expiry raised from 30 min to 8 hours (staff can't be mid-shift logged out)
  - Added refresh token support scaffold (ready to wire in)
"""

from datetime import timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import get_db
import models
from time_utils import utcnow

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── CRITICAL: crash at startup if secret key is missing ──────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "8"))   # was 30 MINUTES

# Pin the Argon2 variant explicitly to Argon2id (OWASP-recommended). passlib's
# argon2 handler already defaults to type "ID", but pinning makes the guarantee
# explicit and stable across library/backend upgrades instead of relying on a
# library default that a future version could change.
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto", argon2__type="ID")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ── Password policy ──────────────────────────────────────────────────────────
# Minimum enforced at registration (see routers/auth.py::register). Length is the
# dominant strength factor (NIST SP 800-63B); the letter+digit rule additionally
# rejects trivially weak single-character-class inputs.
MIN_PASSWORD_LENGTH = 8


def require_strong_password(password: str) -> None:
    """Raise HTTP 400 unless the password meets the minimum policy."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if not any(c.isalpha() for c in password):
        problems.append("at least one letter")
    if not any(c.isdigit() for c in password):
        problems.append("at least one number")
    if problems:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password too weak — must contain " + ", ".join(problems) + ".",
        )


# ── TOTP multi-factor auth (RFC 6238) ────────────────────────────────────────
# Implemented in pure stdlib (hmac/hashlib/base64) rather than adding a pyotp
# dependency — TOTP is ~20 lines and the codes are standard, so Google
# Authenticator / Authy / 1Password all interoperate. Used by the /mfa/* routes
# and enforced at login when a user has mfa_enabled.
import base64
import hashlib
import hmac
import struct
import time as _time


def generate_mfa_secret() -> str:
    """A fresh base32 TOTP secret (160-bit, per RFC 4226 recommendation)."""
    return base64.b32encode(os.urandom(20)).decode("utf-8")


def _hotp(key: bytes, counter: int) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    binary = ((mac[offset] & 0x7F) << 24 | mac[offset + 1] << 16
              | mac[offset + 2] << 8 | mac[offset + 3])
    return str(binary % 1_000_000).zfill(6)


def verify_totp_step(secret_b32: str, code: str, window: int = 1) -> "int | None":
    """The matching 30-second TOTP step for `code`, or None if it doesn't match
    within +/- `window` steps.

    Returning the step (rather than just a bool) is what makes single-use
    enforcement possible: RFC 6238 §5.2 requires that a code be accepted only
    once, and you can't enforce that without knowing WHICH step was accepted.
    See `totp_step_is_replay` and the callers in routers/auth.py.
    """
    if not secret_b32 or not code:
        return None
    code = str(code).strip()
    if not code.isdigit() or len(code) != 6:
        return None
    try:
        key = base64.b32decode(secret_b32, casefold=True)
    except Exception:
        return None
    now_step = int(_time.time() // 30)
    for w in range(-window, window + 1):
        candidate = now_step + w
        if hmac.compare_digest(_hotp(key, candidate), code):
            return candidate
    return None


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    """True if `code` matches the TOTP for `secret_b32` within +/- `window`
    30-second steps (tolerates minor clock skew).

    NOTE: this alone does NOT prevent replay — with window=1 a captured code
    stays valid for ~90 seconds. Authentication paths must use
    `verify_totp_step` + `totp_step_is_replay` so each code is burned after use.
    """
    return verify_totp_step(secret_b32, code, window) is not None


def totp_step_is_replay(last_used_step, step: int) -> bool:
    """True if `step` has already been used (or precedes the last used one).

    Rejecting `<=` rather than `==` also closes the backward-skew half of the
    window: once step N is spent, an attacker replaying an older N-1 code is
    refused too.
    """
    return last_used_step is not None and step <= last_used_step


def mfa_provisioning_uri(email: str, secret_b32: str, issuer: str = "RestaurantAgent") -> str:
    """otpauth:// URI for QR-code enrollment in an authenticator app."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = utcnow() + (
        expires_delta if expires_delta else timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception

    # Session revocation: a token is only valid while its embedded version matches
    # the user's current token_version. Bumping token_version (logout-all, or a
    # response to credential compromise) invalidates every token minted before it.
    # Tokens issued before this feature carry no "ver" claim → default 0, which
    # matches the column default, so they remain valid until the next bump.
    if payload.get("ver", 0) != (user.token_version or 0):
        raise credentials_exception

    return user


def require_role(*allowed_roles: "models.Role"):
    """
    Dependency factory enforcing role-based access control. Returns a FastAPI
    dependency that yields the current user only if their role is one of
    allowed_roles; SUPERADMIN always passes (full system access). Otherwise it
    raises HTTP 403.

    Usage:
        current_user: models.User = Depends(require_role(models.Role.ADMIN))
    """
    allowed = set(allowed_roles)

    async def _require_role_dep(
        current_user: models.User = Depends(get_current_user),
    ) -> models.User:
        if current_user.role == models.Role.SUPERADMIN or current_user.role in allowed:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this action",
        )

    return _require_role_dep
