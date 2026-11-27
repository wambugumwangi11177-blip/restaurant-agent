"""Block a new store manager until the password, PIN, and questionnaire are saved."""
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

_SETUP_ONLY = _ACCOUNT_ONLY + (
    ("POST", "/staff-setup/questionnaire"),
    ("POST", "/staff-setup/questionnaire/reset-self"),
    ("POST", "/staff-setup/opening-profile"),
    ("GET", "/staff-setup/questions"),
)

_STORE_ROLES = (
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.CONTROLLER,
    models.StaffRole.MANAGER,
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
    if user.staff_role not in _STORE_ROLES:
        return
    progress = (
        db.query(models.StaffSetupProgress)
        .filter(models.StaffSetupProgress.user_id == user.id)
        .first()
    )
    if progress is None:
        if not _matches(method, path, _ACCOUNT_ONLY):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="password_change_required",
            )
        return
    if progress.account_completed_at is None:
        if not _matches(method, path, _ACCOUNT_ONLY):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="password_change_required",
            )
        return
    if progress.questionnaire_completed_at is None and not _matches(method, path, _SETUP_ONLY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="questionnaire_required",
        )