"""
backend/tests/test_startup_checks.py
───────────────────────────────────────
The fail-closed boot guard: production must refuse to start with a forgeable
payment callback; non-production only warns.
"""

import pytest

import startup_checks


_MPESA_CREDS = {
    "MPESA_CONSUMER_KEY": "k",
    "MPESA_CONSUMER_SECRET": "s",
    "MPESA_SHORTCODE": "174379",
    "MPESA_PASSKEY": "p",
}


def _set_mpesa(monkeypatch, token: str | None):
    for k, v in _MPESA_CREDS.items():
        monkeypatch.setenv(k, v)
    if token is None:
        monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)
    else:
        monkeypatch.setenv("MPESA_CALLBACK_TOKEN", token)


def test_production_without_callback_token_is_a_hard_problem(monkeypatch):
    monkeypatch.setenv("MPESA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    _set_mpesa(monkeypatch, token=None)

    hard, _soft = startup_checks.collect_problems()
    assert any("MPESA_CALLBACK_TOKEN" in h for h in hard)

    with pytest.raises(RuntimeError):
        startup_checks.enforce_startup_checks()


def test_sandbox_without_callback_token_only_warns(monkeypatch):
    monkeypatch.setenv("MPESA_ENV", "sandbox")
    monkeypatch.setenv("SECRET_KEY", "x")
    _set_mpesa(monkeypatch, token=None)

    hard, soft = startup_checks.collect_problems()
    assert not any("MPESA_CALLBACK_TOKEN" in h for h in hard)
    assert any("MPESA_CALLBACK_TOKEN" in s for s in soft)

    # Must NOT raise outside production.
    startup_checks.enforce_startup_checks()


def test_production_with_callback_token_passes(monkeypatch):
    monkeypatch.setenv("MPESA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    _set_mpesa(monkeypatch, token="a-long-random-secret")

    hard, _soft = startup_checks.collect_problems()
    assert hard == []
    startup_checks.enforce_startup_checks()  # no raise


def test_app_env_production_also_triggers_enforcement(monkeypatch):
    monkeypatch.delenv("MPESA_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    _set_mpesa(monkeypatch, token=None)

    assert startup_checks.is_production() is True
    with pytest.raises(RuntimeError):
        startup_checks.enforce_startup_checks()


def test_mpesa_not_configured_token_still_required_in_production(monkeypatch):
    # CYB-103: the CallBackURL token is the callback's ONLY authentication, so
    # production requires it even with no Daraja creds configured (creds don't
    # authenticate the inbound callback; the token does).
    monkeypatch.setenv("MPESA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    for k in _MPESA_CREDS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert any("MPESA_CALLBACK_TOKEN" in h for h in hard)


def test_local_storage_backend_in_production_is_a_soft_warning(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "set-so-other-checks-run")  # CYB-103 guard satisfied
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)  # unset == "local"

    hard, soft = startup_checks.collect_problems()
    assert not any("STORAGE_BACKEND" in h for h in hard)
    assert any("STORAGE_BACKEND" in s for s in soft)

    # Soft, not hard: must NOT block boot.
    startup_checks.enforce_startup_checks()


def test_s3_storage_backend_in_production_has_no_warning(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")

    _hard, soft = startup_checks.collect_problems()
    assert not any("STORAGE_BACKEND" in s for s in soft)


def test_local_storage_backend_outside_production_has_no_warning(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("MPESA_ENV", raising=False)
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)

    _hard, soft = startup_checks.collect_problems()
    assert not any("STORAGE_BACKEND" in s for s in soft)


def test_unconfigured_smtp_in_production_is_a_soft_warning(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "set-so-other-checks-run")  # CYB-103 guard satisfied
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not any("SMTP" in h for h in hard)
    assert any("SMTP" in s for s in soft)

    # Soft, not hard: must NOT block boot.
    startup_checks.enforce_startup_checks()


def test_configured_smtp_in_production_has_no_warning(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "s3cret")

    _hard, soft = startup_checks.collect_problems()
    assert not any("SMTP" in s for s in soft)


def test_unconfigured_smtp_outside_production_has_no_warning(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("MPESA_ENV", raising=False)
    monkeypatch.setenv("SECRET_KEY", "x")
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)

    _hard, soft = startup_checks.collect_problems()
    assert not any("SMTP" in s for s in soft)


def test_production_without_any_mpesa_does_not_require_a_callback_token(monkeypatch):
    """
    A deployment that does not use M-Pesa at all must still boot.

    The gate was unconditional, so a tenant taking no M-Pesa payments could not
    start in production without inventing a token for a provider it never
    calls. That is not a security property, it is a ritual — and the real
    protection is elsewhere: _verify_mpesa_token() 403s every callback while
    the token is unset, credentials or not (CYB-103).

    The warning still appears; it just does not block the boot.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/app")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.delenv("MPESA_ENV", raising=False)
    for k in _MPESA_CREDS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not any("MPESA_CALLBACK_TOKEN" in h for h in hard)
    assert any("MPESA_CALLBACK_TOKEN" in s for s in soft)

    # The whole point: this boots.
    startup_checks.enforce_startup_checks()


def test_declaring_mpesa_env_restores_the_hard_requirement(monkeypatch):
    """Setting MPESA_ENV says the integration is live, even before creds land."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/app")
    monkeypatch.setenv("MPESA_ENV", "sandbox")
    for k in _MPESA_CREDS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert any("MPESA_CALLBACK_TOKEN" in h for h in hard)


def test_credentials_alone_restore_the_hard_requirement(monkeypatch):
    """Daraja creds present means money can move; the token is mandatory."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/app")
    monkeypatch.delenv("MPESA_ENV", raising=False)
    for k, v in _MPESA_CREDS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert any("MPESA_CALLBACK_TOKEN" in h for h in hard)
