"""
backend/tests/test_notifications_health.py
────────────────────────────────────────────
The notification chain's failure mode is silence: a send with no Twilio config
returns not_configured, gets logged, and every caller shrugs. These tests pin
down that the silence is now *detected* — by the boot guard, by the health
endpoint, and with the right severity (a dead transport is `down`; a missing SMS
fallback is only `degraded`, because over-paging is how monitors get muted).
"""

import importlib

import pytest

import models
import notifications_health
from ai.whatsapp import twilio_client


@pytest.fixture
def twilio_env(monkeypatch):
    """
    Set Twilio env vars and reload the transport so the module-level config
    `send()` branches on actually changes.

    `twilio_client` captures TWILIO_* at import time (see its module body), so
    monkeypatching the env alone would leave both the transport and
    `notifications_health` reading stale values — the reload is what makes this
    test exercise the real code path. Reloaded again on teardown so a later test
    never inherits this one's credentials.
    """

    def _apply(**env):
        for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                    "TWILIO_WHATSAPP_FROM", "TWILIO_SMS_FROM"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        importlib.reload(twilio_client)
        return twilio_client

    yield _apply
    monkeypatch.undo()
    importlib.reload(twilio_client)


# A production-shaped config: own approved WhatsApp sender (NOT the sandbox
# default) plus an SMS sender, so nothing here trips a warning.
FULLY_CONFIGURED = {
    "TWILIO_ACCOUNT_SID": "AC" + "0" * 32,
    "TWILIO_AUTH_TOKEN": "token123",
    "TWILIO_WHATSAPP_FROM": "whatsapp:+254700111222",
    "TWILIO_SMS_FROM": "LEVIII",
}


# ── transport ────────────────────────────────────────────────────────────────

def test_no_credentials_is_down(twilio_env):
    twilio_env()  # nothing set

    report = notifications_health.overall()

    assert report["status"] == "down"
    assert not report["transport"]["any_channel_ready"]
    assert any("TWILIO_ACCOUNT_SID" in p for p in report["problems"])


def test_credentials_without_any_from_number_is_down(twilio_env):
    # The subtle outage: billing is fine, the client builds, and every send
    # still returns not_configured because there is no address to send from.
    # TWILIO_WHATSAPP_FROM defaults to the sandbox rather than empty, so an
    # explicit "" is what actually clears the channel.
    twilio_env(
        TWILIO_ACCOUNT_SID="AC" + "0" * 32,
        TWILIO_AUTH_TOKEN="token123",
        TWILIO_WHATSAPP_FROM="",
    )

    report = notifications_health.overall()

    assert report["status"] == "down"
    assert report["transport"]["credentials_configured"]
    assert any("neither" in p for p in report["problems"])


def test_unset_whatsapp_sender_falls_back_to_the_sandbox_and_warns(twilio_env):
    """
    The most deceptive failure in the chain, and the reason this check exists:
    with TWILIO_WHATSAPP_FROM unset, twilio_client defaults to Twilio's *shared
    public sandbox* number. Twilio accepts the send and reports success, so
    nothing anywhere looks wrong — but delivery only reaches handsets that
    texted the sandbox join code, and each opt-in dies after 72h. A real owner
    on a real deploy would simply never receive their morning briefing.
    """
    twilio_env(TWILIO_ACCOUNT_SID="AC" + "0" * 32, TWILIO_AUTH_TOKEN="token123")

    report = notifications_health.overall()

    assert report["transport"]["whatsapp_using_sandbox"]
    assert report["status"] == "degraded"
    assert any("sandbox" in w for w in report["warnings"])


def test_whatsapp_only_is_degraded_not_down(twilio_env):
    twilio_env(
        TWILIO_ACCOUNT_SID="AC" + "0" * 32,
        TWILIO_AUTH_TOKEN="token123",
        TWILIO_WHATSAPP_FROM="whatsapp:+254700111222",
    )

    report = notifications_health.overall()

    # Delivery works; only the fallback for non-WhatsApp customers is missing.
    assert report["status"] == "degraded"
    assert report["problems"] == []
    assert any("TWILIO_SMS_FROM" in w for w in report["warnings"])


def test_fully_configured_transport_is_ok(twilio_env):
    twilio_env(**FULLY_CONFIGURED)

    report = notifications_health.overall()

    assert report["status"] == "ok"
    assert report["transport"]["whatsapp_ready"]
    assert report["transport"]["sms_ready"]


def test_transport_status_tracks_the_module_send_actually_uses(twilio_env):
    """Guards the reason this module reads twilio_client attributes rather than
    os.getenv: a health check that disagrees with the transport is worse than
    none, because it certifies a broken deploy as healthy."""
    twilio_env(**FULLY_CONFIGURED)
    assert notifications_health.transport_status()["credentials_configured"]

    twilio_env()
    assert not notifications_health.transport_status()["credentials_configured"]


# ── owner routing ────────────────────────────────────────────────────────────

def test_restaurant_without_owner_phone_is_flagged(db_session, twilio_env, monkeypatch):
    # The legacy env fallback in brain.owner_phone_for would otherwise mask this
    # on a machine that happens to have OWNER_PHONE set.
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    twilio_env(**FULLY_CONFIGURED)

    db_session.add(models.Restaurant(name="Reachable", owner_phone="+254700000001"))
    db_session.add(models.Restaurant(name="Silent", owner_phone=None))
    db_session.commit()

    report = notifications_health.overall(db_session)

    assert report["owner_routing"]["restaurants"] == 2
    assert report["owner_routing"]["without_owner_phone"] == 1
    assert "Silent" in report["owner_routing"]["unreachable_names"]
    assert report["status"] == "degraded"


# ── delivery history ─────────────────────────────────────────────────────────

def _log(db, restaurant_id, status, n=1):
    for _ in range(n):
        db.add(models.AgentMessage(
            restaurant_id=restaurant_id, recipient="+254700000001",
            message_body="x", message_type="test", status=status,
        ))
    db.commit()


def test_opt_out_suppression_is_not_counted_as_failure(db_session, twilio_env, monkeypatch):
    """A healthy STOP list must not read as an outage — otherwise respecting
    consent looks like breakage and the signal gets ignored."""
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    twilio_env(**FULLY_CONFIGURED)
    r = models.Restaurant(name="R", owner_phone="+254700000001")
    db_session.add(r)
    db_session.commit()

    _log(db_session, r.id, "suppressed_optout", n=40)
    _log(db_session, r.id, "sent", n=10)

    report = notifications_health.overall(db_session)

    assert report["delivery"]["suppressed_optout"] == 40
    assert report["delivery"]["failure_rate"] == 0.0
    assert report["status"] == "ok"


def test_high_recent_failure_rate_is_degraded(db_session, twilio_env, monkeypatch):
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    twilio_env(**FULLY_CONFIGURED)
    r = models.Restaurant(name="R", owner_phone="+254700000001")
    db_session.add(r)
    db_session.commit()

    _log(db_session, r.id, "error", n=10)
    _log(db_session, r.id, "sent", n=10)

    report = notifications_health.overall(db_session)

    assert report["delivery"]["failure_rate"] == 0.5
    assert report["status"] == "degraded"
    assert any("failed" in w for w in report["warnings"])


def test_a_few_failures_on_low_volume_is_not_degraded(db_session, twilio_env, monkeypatch):
    """Below MIN_SENDS_FOR_RATE a rate is noise; alerting on it trains people to
    ignore the alert."""
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    twilio_env(**FULLY_CONFIGURED)
    r = models.Restaurant(name="R", owner_phone="+254700000001")
    db_session.add(r)
    db_session.commit()

    _log(db_session, r.id, "error", n=2)

    report = notifications_health.overall(db_session)

    assert report["status"] == "ok"


# ── scheduler ────────────────────────────────────────────────────────────────

def test_expected_jobs_match_the_scheduler_actually_registered():
    """
    Pins notifications_health's job list to main._start_scheduler. Two of these
    jobs (stock_check, slow_day_check) previously existed as functions that were
    never registered — the bug this list exists to keep from recurring — so a
    drifting list would quietly stop describing reality.
    """
    import inspect

    import main

    source = inspect.getsource(main._start_scheduler)
    for job_id in notifications_health.scheduled_jobs_status()["expected_jobs"]:
        assert f'id="{job_id}"' in source, f"{job_id} is claimed but not registered"


# ── wiring: boot guard + health endpoint ─────────────────────────────────────

def test_startup_checks_warn_but_never_block_boot_on_notifications(twilio_env, monkeypatch):
    """
    Deliberate severity choice: a restaurant whose POS won't boot because
    WhatsApp is misconfigured is worse off than one whose briefing is late. So
    this is soft even in production.
    """
    import startup_checks

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    # Clear M-Pesa creds so the (unrelated) forgeable-callback rule can't be the
    # thing that raises and mask what this test is asserting.
    for key in ("MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET",
                "MPESA_SHORTCODE", "MPESA_PASSKEY"):
        monkeypatch.delenv(key, raising=False)
    twilio_env()  # notifications fully dead

    hard, soft = startup_checks.collect_problems()

    assert any("notifications:" in s for s in soft)
    assert not any("notifications" in h for h in hard)
    startup_checks.enforce_startup_checks()  # must not raise


def test_health_endpoint_reports_503_when_notifications_are_down(client, twilio_env):
    twilio_env()

    resp = client.get("/health/notifications")

    assert resp.status_code == 503
    assert resp.json()["detail"]["status"] == "down"


def test_health_endpoint_reports_200_when_configured(client, twilio_env):
    twilio_env(**FULLY_CONFIGURED)

    resp = client.get("/health/notifications")

    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")


def test_health_endpoint_leaks_no_credentials(client, twilio_env):
    twilio_env(**FULLY_CONFIGURED)

    body = client.get("/health/notifications").text

    assert FULLY_CONFIGURED["TWILIO_AUTH_TOKEN"] not in body
    assert FULLY_CONFIGURED["TWILIO_ACCOUNT_SID"] not in body
