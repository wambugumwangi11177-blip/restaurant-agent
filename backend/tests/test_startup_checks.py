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


def test_mpesa_not_configured_means_no_token_requirement(monkeypatch):
    # No M-Pesa creds → nothing to forge → token not required even in production.
    monkeypatch.setenv("MPESA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    for k in _MPESA_CREDS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert hard == []
