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


def test_retired_gateway_configuration_does_not_block_startup(monkeypatch):
    monkeypatch.setenv("MPESA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    _set_mpesa(monkeypatch, token=None)

    hard, _soft = startup_checks.collect_problems()
    assert not any("MPESA_CALLBACK_TOKEN" in h for h in hard)

    startup_checks.enforce_startup_checks()


def test_retired_callback_token_has_no_warning(monkeypatch):
    monkeypatch.setenv("MPESA_ENV", "sandbox")
    monkeypatch.setenv("SECRET_KEY", "x")
    _set_mpesa(monkeypatch, token=None)

    hard, soft = startup_checks.collect_problems()
    assert not any("MPESA_CALLBACK_TOKEN" in h for h in hard)
    assert not any("MPESA_CALLBACK_TOKEN" in s for s in soft)

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
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        startup_checks.enforce_startup_checks()


def test_removed_gateway_does_not_require_credentials(monkeypatch):
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
    assert not any("MPESA_CALLBACK_TOKEN" in h for h in hard)


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


def test_retired_mpesa_gate_is_gone_entirely(monkeypatch):
    """M-Pesa was retired (6aee044). The boot gate went with it.

    Three tests used to assert a soft MPESA_CALLBACK_TOKEN warning survived in
    production. They came back during the consolidation merge alongside the
    retirement that deleted the check they assert, and failed on master from
    2026-09-20. The contract now is simply: startup says nothing about M-Pesa.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/app")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("MPESA_ENV", "production")          # even declared live
    for k, v in _MPESA_CREDS.items():
        monkeypatch.setenv(k, v)                           # even fully credentialed
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not any("MPESA" in problem for problem in hard + soft)

    startup_checks.enforce_startup_checks()                # and it boots
