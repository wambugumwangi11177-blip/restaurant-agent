"""
backend/tests/test_startup_checks.py
───────────────────────────────────────
The fail-closed boot guard: production must refuse to start with a forgeable
payment callback; non-production only warns.
"""

import pytest

import environment
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


def _set_prod_baseline(monkeypatch):
    """The other config a production boot requires, so a test that is asserting
    about ONE check isn't tripped by the others. DATABASE_URL and CORS_ORIGINS
    became hard problems in production when the environment gate was fixed."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/app")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")


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
    _set_prod_baseline(monkeypatch)
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
    _set_prod_baseline(monkeypatch)
    for k in _MPESA_CREDS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert hard == []


# ── Environment resolution (environment.py) ──────────────────────────────────
#
# The bug these cover: APP_ENV was set nowhere in the repo, so is_production()
# returned False in production and every hard check above silently degraded to
# a warning. The gate is only as good as the environment signal feeding it.


def _clear_env_signals(monkeypatch):
    for k in ("APP_ENV", "MPESA_ENV", "CI"):
        monkeypatch.delenv(k, raising=False)


@pytest.mark.parametrize("declared", ["local", "ci", "staging", "production"])
def test_app_env_resolves_each_valid_environment(monkeypatch, declared):
    _clear_env_signals(monkeypatch)
    monkeypatch.setenv("APP_ENV", declared)
    assert environment.current_env() == declared
    assert environment.is_production() is (declared == "production")


def test_unrecognised_app_env_resolves_to_production_not_local(monkeypatch):
    # A typo must not silently unlock permissive local-dev behaviour.
    _clear_env_signals(monkeypatch)
    monkeypatch.setenv("APP_ENV", "prod")
    assert environment.current_env() == "production"
    assert environment.is_production() is True


def test_environment_is_inferred_when_app_env_undeclared(monkeypatch):
    _clear_env_signals(monkeypatch)
    assert environment.current_env() == "local"
    assert environment.env_declared() is False

    monkeypatch.setenv("CI", "true")
    assert environment.current_env() == "ci"

    # Real money moving is treated as production even with APP_ENV undeclared.
    monkeypatch.setenv("MPESA_ENV", "production")
    assert environment.current_env() == "production"


def test_undeclared_app_env_is_warned_about(monkeypatch):
    _clear_env_signals(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "x")
    _set_prod_baseline(monkeypatch)

    _hard, soft = startup_checks.collect_problems()
    assert any("APP_ENV" in s for s in soft)


# ── DATABASE_URL: the silent-SQLite-fallback gap ─────────────────────────────


def test_missing_database_url_is_hard_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert any("DATABASE_URL" in h for h in hard)


def test_sqlite_database_url_is_hard_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./restaurant.db")

    hard, _soft = startup_checks.collect_problems()
    assert any("SQLite" in h for h in hard)


def test_missing_database_url_only_warns_outside_production(monkeypatch):
    _clear_env_signals(monkeypatch)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not any("DATABASE_URL" in h for h in hard)
    assert any("DATABASE_URL" in s for s in soft)
    startup_checks.enforce_startup_checks()  # must not raise


# ── CORS: promoted from soft to hard in production ───────────────────────────


def test_missing_cors_origins_is_hard_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/app")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert any("CORS_ORIGINS" in h for h in hard)

    with pytest.raises(RuntimeError):
        startup_checks.enforce_startup_checks()


def test_production_cors_default_no_longer_contains_prod_origin():
    """The dev fallback origin list must not carry the real production domain —
    that made every environment accept the production frontend origin."""
    import pathlib
    source = pathlib.Path(__file__).resolve().parents[1] / "main.py"
    text = source.read_text(encoding="utf-8")
    default_line = next(
        line for line in text.splitlines() if line.startswith("default_origins")
    )
    assert "vercel.app" not in default_line
    assert "localhost" in default_line
