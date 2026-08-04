"""
backend/notifications_health.py
────────────────────────────────
Is the notification chain actually alive?

The whole product promise ("every morning it tells your managers the three
things to do today") rides on outbound WhatsApp/SMS. But that chain fails
*silently*: `twilio_client.send()` returns `{"status": "not_configured"}` and
writes a log line when credentials are missing, and every caller treats a failed
send as best-effort. Nothing raises. Nothing alerts. A deploy that forgot
`TWILIO_AUTH_TOKEN` looks perfectly healthy — orders work, the dashboard works —
while not one owner alert has left the building.

This module is the single place that answers "would a notification actually go
out right now, and have recent ones been going out?" It is deliberately:

  • **read-only** — never sends anything, safe to poll from a monitor;
  • **honest** — it reads the same module-level config `twilio_client.send()`
    reads, not `os.getenv`, so it reports what the transport would really do
    (those vars are captured at import; re-reading the env here would happily
    report "configured" for a process whose transport is not);
  • **shared** — `startup_checks`, `GET /health/notifications`, and
    `execution/verify_notifications.py` all call it, so there is one definition
    of "notifications are broken" instead of three that drift.

Severity model, matching how much each failure actually costs:
  down      — nothing can be delivered at all (no transport configured).
  degraded  — delivery is possible but partly broken (no owner phone on some
              restaurants, a high recent failure rate, no SMS fallback).
  ok        — transport configured and recent sends are landing.

Deliberately NOT a boot blocker: a restaurant whose POS won't start because
Twilio is misconfigured is strictly worse off than one whose morning briefing is
late. Production logs a loud warning (startup_checks) and the monitor endpoint
goes unhealthy — that is the right blast radius.
"""

from datetime import timedelta

from time_utils import utcnow

# Import the module, not its names: the tests reload twilio_client after setting
# env vars, and a `from ... import CONFIGURED` would pin the pre-reload value.
from ai.whatsapp import twilio_client

# Sends whose status is anything other than these never reached the provider.
_DELIVERED_STATUSES = frozenset({"sent"})
# A suppressed message is a *correct* outcome (the customer replied STOP), not a
# failure — counting it as one would make a healthy opt-out list look like an
# outage.
_NOT_A_FAILURE = frozenset({"sent", "suppressed_optout"})

# How far back the delivery-health window looks, and how many sends must exist
# in it before a failure *rate* means anything (3 failures out of 3 messages is
# noise on a quiet Tuesday; the same rate over 50 is an outage).
FAILURE_WINDOW_HOURS = 24
MIN_SENDS_FOR_RATE = 10
FAILURE_RATE_DEGRADED = 0.25

# Twilio's shared public WhatsApp sandbox number, which is also
# twilio_client's *default* for TWILIO_WHATSAPP_FROM. That default is a
# convenience for local development and a trap in production: the sandbox only
# delivers to handsets that have texted its join code, and each opt-in expires
# after 72 hours of inactivity. A deploy that forgot to set the real sender
# therefore reports "sent" from Twilio and reaches almost nobody — the single
# most deceptive failure in this chain, because it produces no errors at all.
TWILIO_SANDBOX_FROM = "whatsapp:+14155238886"


def transport_status() -> dict:
    """
    What the Twilio transport would do with a send right now, per channel.

    Reports `twilio_client`'s live module state — the exact values `send()`
    branches on — so this can never disagree with the real transport.
    """
    whatsapp_from = twilio_client.TWILIO_WHATSAPP_FROM
    whatsapp_ready = bool(twilio_client.CONFIGURED and whatsapp_from)
    sms_ready = bool(twilio_client.CONFIGURED and twilio_client.TWILIO_SMS_FROM)
    return {
        "credentials_configured": bool(twilio_client.CONFIGURED),
        "whatsapp_ready": whatsapp_ready,
        "sms_ready": sms_ready,
        "whatsapp_from_set": bool(whatsapp_from),
        "sms_from_set": bool(twilio_client.TWILIO_SMS_FROM),
        "whatsapp_using_sandbox": whatsapp_from == TWILIO_SANDBOX_FROM,
        "any_channel_ready": whatsapp_ready or sms_ready,
    }


def owner_routing_status(db) -> dict:
    """
    Which active restaurants could actually be reached by an owner alert.

    A restaurant with no `owner_phone` (and no legacy OWNER_PHONE_{id} env
    fallback) is skipped with a log line by `brain.send_to_owner` — every
    briefing, stock alert, and slow-day alert for that tenant silently never
    happens. That is invisible until someone asks why they get nothing.
    """
    import models
    from ai.whatsapp.brain import owner_phone_for

    # Every restaurant, unfiltered — deliberately mirroring
    # `brain.run_morning_briefing`, which iterates `Restaurant` with no filter
    # (there is no is_active column on this model). Narrowing here would let a
    # tenant that really does get briefed slip out of the health picture.
    restaurants = db.query(models.Restaurant).all()
    unreachable = [r.name or f"id={r.id}" for r in restaurants if not owner_phone_for(r)]
    return {
        "restaurants": len(restaurants),
        "without_owner_phone": len(unreachable),
        "unreachable_names": unreachable[:20],
    }


def delivery_status(db) -> dict:
    """
    Recent outbound results from the message log — proof of delivery, not just
    of configuration. Config can be perfect while every send errors (suspended
    Twilio account, unverified sandbox number, exhausted balance).
    """
    import models

    since = utcnow() - timedelta(hours=FAILURE_WINDOW_HOURS)
    rows = (
        db.query(models.AgentMessage.status)
        .filter(models.AgentMessage.created_at >= since)
        .all()
    )
    total = len(rows)
    delivered = sum(1 for (s,) in rows if s in _DELIVERED_STATUSES)
    suppressed = sum(1 for (s,) in rows if s == "suppressed_optout")
    failed = sum(1 for (s,) in rows if s not in _NOT_A_FAILURE)
    considered = total - suppressed
    return {
        "window_hours": FAILURE_WINDOW_HOURS,
        "total": total,
        "delivered": delivered,
        "suppressed_optout": suppressed,
        "failed": failed,
        "failure_rate": round(failed / considered, 3) if considered else 0.0,
    }


def scheduled_jobs_status() -> dict:
    """
    Are the cron jobs that *trigger* notifications actually registered?

    `main._start_scheduler` swallows both ImportError and any startup exception
    by design (a dead scheduler must not take the API down). The cost is that
    "APScheduler isn't installed" degrades to one WARNING line at boot and no
    scheduled alert ever fires again. Checking importability here surfaces that
    class of failure without needing the running scheduler instance.
    """
    try:
        import apscheduler  # noqa: F401

        available = True
    except ImportError:
        available = False
    return {
        "apscheduler_available": available,
        # Kept in sync with main._start_scheduler by test_notifications_health.
        "expected_jobs": [
            "morning_briefing",
            "po_late_check",
            "stock_check",
            "slow_day_check",
            "reservation_reminders",
            "learning_cycle",
        ],
    }


def overall(db=None) -> dict:
    """
    Full picture with a single verdict. `db` is optional so the transport half
    can be checked with no database (startup, or a preflight against a host
    whose DB is unreachable).
    """
    transport = transport_status()
    jobs = scheduled_jobs_status()

    problems: list[str] = []
    warnings: list[str] = []

    if not transport["credentials_configured"]:
        problems.append(
            "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set — every outbound "
            "WhatsApp and SMS silently returns not_configured"
        )
    elif not transport["any_channel_ready"]:
        problems.append(
            "Twilio credentials are set but neither TWILIO_WHATSAPP_FROM nor "
            "TWILIO_SMS_FROM is — there is no channel to send from"
        )
    else:
        if not transport["whatsapp_ready"]:
            warnings.append("TWILIO_WHATSAPP_FROM not set — WhatsApp sends cannot go out")
        elif transport["whatsapp_using_sandbox"]:
            warnings.append(
                f"TWILIO_WHATSAPP_FROM is still Twilio's shared sandbox number "
                f"({TWILIO_SANDBOX_FROM}) — sends are accepted and reported as sent, but "
                f"only reach handsets that texted the sandbox join code, and each opt-in "
                f"expires after 72h. Set your own approved WhatsApp sender before go-live."
            )
        if not transport["sms_ready"]:
            warnings.append(
                "TWILIO_SMS_FROM not set — the SMS fallback is dead, so owners and "
                "customers who are not on WhatsApp receive nothing"
            )

    if not jobs["apscheduler_available"]:
        problems.append(
            "APScheduler is not installed — no morning briefing, stock alert, "
            "slow-day alert, or reservation reminder will ever fire"
        )

    result = {"transport": transport, "scheduler": jobs}

    if db is not None:
        routing = owner_routing_status(db)
        delivery = delivery_status(db)
        result["owner_routing"] = routing
        result["delivery"] = delivery

        if routing["restaurants"] and routing["without_owner_phone"]:
            warnings.append(
                f"{routing['without_owner_phone']} of {routing['restaurants']} "
                f"restaurants have no owner phone — every owner alert for them is dropped"
            )
        considered = delivery["total"] - delivery["suppressed_optout"]
        if considered >= MIN_SENDS_FOR_RATE and delivery["failure_rate"] >= FAILURE_RATE_DEGRADED:
            warnings.append(
                f"{delivery['failed']} of the last {considered} sends failed "
                f"({delivery['failure_rate']:.0%}) in {FAILURE_WINDOW_HOURS}h"
            )

    if problems:
        status = "down"
    elif warnings:
        status = "degraded"
    else:
        status = "ok"

    result["status"] = status
    result["problems"] = problems
    result["warnings"] = warnings
    return result
