"""Block a new storekeeper until the account step, then until recipes, are done.

Existing staff (no setup row, must_change_password false) are unchanged.
"""
from fastapi import HTTPException, status
import models


def _path(request) -> tuple[str, str]:
    return request.method.upper(), (request.url.path or "/").rstrip("/") or "/"


def _matches(method: str, path: str, allowed: tuple[tuple[str, str], ...]) -> bool:
    return any(method == want_method and path.endswith(suffix) for want_method, suffix in allowed)


_ACCOUNT_ONLY = (
    ("GET", "/auth/me"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/logout-all"),
    ("GET", "/staff-setup"),
    ("POST", "/staff-setup/account"),
)

_UNTIL_RECIPES = _ACCOUNT_ONLY + (
    ("GET", "/store/recipes"),
    ("POST", "/store/recipes"),
    ("POST", "/staff-setup/recipes"),
)


def enforce_storekeeper_setup(user: models.User, request, db) -> None:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return
    method, path = _path(request)
    if user.must_change_password and not _matches(method, path, _ACCOUNT_ONLY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password_change_required",
        )
    if user.staff_role != models.StaffRole.STOCKKEEPER:
        return
    progress = (
        db.query(models.StaffSetupProgress)
        .filter(models.StaffSetupProgress.user_id == user.id)
        .first()
    )
    if progress is None or progress.recipes_completed_at is not None:
        return
    if progress.account_completed_at is None:
        if not _matches(method, path, _ACCOUNT_ONLY):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="password_change_required",
            )
        return
    if not _matches(method, path, _UNTIL_RECIPES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="recipes_required",
        )
