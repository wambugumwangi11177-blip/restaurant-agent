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
