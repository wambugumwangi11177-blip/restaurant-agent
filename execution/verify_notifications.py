"""
execution/verify_notifications.py
──────────────────────────────────
Preflight the outbound notification chain — the answer to "will the owner
actually get their morning briefing tomorrow?"

Run this before a demo, before onboarding a restaurant, and after any change to
Twilio config. It is the deterministic (layer-3) counterpart to
`backend/notifications_health.py`: that module decides what "broken" means, this
script points it at a target and prints a verdict a human can act on.

Two modes:

  READ-ONLY (default) — never sends a message, never writes a row. Checks
      credentials, sender numbers, per-restaurant owner routing, scheduler job
      registration, and the recent send-failure rate. Safe against production.

  LIVE (--send +2547XXXXXXXX) — actually puts one message through the real
      transport to a number you name. This is the only check that proves
      delivery rather than configuration, and it is opt-in because it spends
      real credit and messages a real handset. It is what catches a WhatsApp
      sender that is configured, billed, and still silently undeliverable
      (unjoined sandbox, unapproved template, suspended account).

Targets:
  --local  (default)  import the backend in-process and read its DATABASE_URL
  --url https://host  hit a deployed instance's GET /health/notifications

Exit codes are CI/monitor friendly:
  0 = ok        2 = degraded (delivery works, something is wrong)
  1 = down      3 = could not run the check at all

Usage:
    py execution/verify_notifications.py
    py execution/verify_notifications.py --url https://api.example.com
    py execution/verify_notifications.py --send +254700000001 --channel sms
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"

EXIT_OK, EXIT_DOWN, EXIT_DEGRADED, EXIT_ERROR = 0, 1, 2, 3

TICK = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}


def _load_backend():
    """
    Put `backend/` on the path and load its .env, exactly as the app does.

    The path insert must happen before the imports because every backend module
    uses top-level absolute imports (`import models`, `from database import ...`)
    that assume `backend/` is the working root.
    """
    sys.path.insert(0, str(BACKEND))
    try:
        from dotenv import load_dotenv

        load_dotenv(BACKEND / ".env")
    except ImportError:
        pass  # python-dotenv is optional; platform env vars work either way


# ── rendering ────────────────────────────────────────────────────────────────

def _print_report(report: dict, source: str) -> None:
    status = report["status"]
    print("=" * 72)
    print(f"NOTIFICATION PREFLIGHT — {source}")
    print("=" * 72)

    t = report.get("transport", {})
    print("\nTransport (Twilio)")
    _line("Credentials (SID + auth token)", t.get("credentials_configured"))
    # The sandbox note only means anything once credentials exist; showing it on
    # a deploy with no Twilio at all just buries the real problem.
    sandbox = t.get("whatsapp_using_sandbox") and t.get("whatsapp_ready")
    _line("WhatsApp sender", t.get("whatsapp_ready"),
          note="using Twilio's shared SANDBOX number" if sandbox else "")
    _line("SMS sender (fallback for non-WhatsApp phones)", t.get("sms_ready"), soft=True)

    s = report.get("scheduler", {})
    print("\nScheduled triggers")
    _line("APScheduler installed", s.get("apscheduler_available"))
    for job in s.get("expected_jobs", []):
        print(f"       · {job}")

    if "owner_routing" in report:
        r = report["owner_routing"]
        print("\nOwner routing")
        reachable = r["restaurants"] - r["without_owner_phone"]
        _line(f"Restaurants with an owner phone ({reachable}/{r['restaurants']})",
              r["without_owner_phone"] == 0, soft=True)
        for name in r.get("unreachable_names", []):
            print(f"       · no phone: {name}")

    if "delivery" in report:
        d = report["delivery"]
        print(f"\nDelivery, last {d['window_hours']}h")
        print(f"       sent {d['delivered']} · failed {d['failed']} · "
              f"suppressed (opt-out) {d['suppressed_optout']} · "
              f"failure rate {d['failure_rate']:.0%}")

    for p in report.get("problems", []):
        print(f"\n{TICK['fail']} {p}")
    for w in report.get("warnings", []):
        print(f"\n{TICK['warn']} {w}")

    print("\n" + "-" * 72)
    verdict = {
        "ok": "OK — notifications will go out.",
        "degraded": "DEGRADED — messages can be sent, but something above will silently cost you delivery.",
        "down": "DOWN — no notification can be delivered right now.",
    }[status]
    print(f"{status.upper()}: {verdict}")
    print("-" * 72)


def _line(label: str, ok, *, soft: bool = False, note: str = "") -> None:
    if ok:
        mark = TICK["warn"] if note else TICK["ok"]
    else:
        mark = TICK["warn"] if soft else TICK["fail"]
    suffix = f"  ← {note}" if note else ""
    print(f"  {mark} {label}{suffix}")


# ── modes ────────────────────────────────────────────────────────────────────

def check_local() -> dict:
    _load_backend()
    from notifications_health import overall

    try:
        from database import SessionLocal

        db = SessionLocal()
        try:
            return overall(db)
        finally:
            db.close()
    except Exception as exc:
        # A dead database must not hide the transport verdict — config problems
        # are exactly what you want to see when the DB is also misconfigured.
        print(f"{TICK['warn']} database unreachable ({exc}); checking transport only\n")
        return overall()


def check_remote(base_url: str) -> dict:
    import json
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/health/notifications"
    try:
        # nosec B310 — the URL is typed by the operator running the preflight
        # against their own deployment, not attacker-controlled input.
        with urllib.request.urlopen(url, timeout=15) as resp:  # nosec B310
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            # The documented "down" response — the body carries the full report.
            body = json.loads(exc.read())
            return body.get("detail", body)
        raise


def send_live_test(to_number: str, channel: str) -> int:
    """
    Put one real message through the transport. Proves delivery, costs credit.

    Returns a process exit code. This is the only check that can catch a
    configured-but-undeliverable sender, so its failure is a hard `down`.
    """
    _load_backend()
    from ai.whatsapp import twilio_client

    print(f"\nLive test → {to_number} over {channel}")
    result = twilio_client.send(
        to_number,
        "Leviii preflight: notifications are working. No action needed.",
        channel=channel,
    )
    status = result.get("status")
    if status == "sent":
        print(f"  {TICK['ok']} accepted by Twilio (sid {result.get('sid')})")
        print("  NOTE: 'accepted' is not 'read'. Confirm the handset actually received it —")
        print("        an unjoined WhatsApp sandbox accepts sends that never arrive.")
        return EXIT_OK
    print(f"  {TICK['fail']} transport returned: {status}")
    return EXIT_DOWN


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Check a deployed instance instead of the local backend")
    parser.add_argument("--send", metavar="E164",
                        help="Also send ONE real message to this number (costs credit)")
    parser.add_argument("--channel", default="whatsapp", choices=["whatsapp", "sms"],
                        help="Channel for --send (default: whatsapp)")
    args = parser.parse_args()

    try:
        if args.url:
            report = check_remote(args.url)
            source = args.url
        else:
            report = check_local()
            source = f"local backend (DATABASE_URL={_safe_db()})"
    except Exception as exc:
        print(f"{TICK['fail']} preflight could not run: {exc}", file=sys.stderr)
        return EXIT_ERROR

    _print_report(report, source)

    code = {"ok": EXIT_OK, "degraded": EXIT_DEGRADED, "down": EXIT_DOWN}[report["status"]]

    if args.send:
        if args.url:
            # Sending runs through THIS machine's transport, which is not the
            # deployed one — a pass here would say nothing about the target.
            print(f"\n{TICK['warn']} --send is ignored with --url: it would test this "
                  f"machine's Twilio config, not {args.url}'s.")
        else:
            send_code = send_live_test(args.send, args.channel)
            # NOT max(): the exit codes are identifiers, not a severity ranking
            # (down=1 sorts *below* degraded=2), so max() would report a failed
            # live send on a merely-degraded config as "degraded" and hide the
            # more serious result. A failed live send is definitive — the
            # transport did not accept a real message — so it wins outright.
            if send_code != EXIT_OK:
                code = send_code

    return code


def _safe_db() -> str:
    """DB target with credentials stripped — this output gets pasted into chats."""
    from urllib.parse import urlparse

    url = os.getenv("DATABASE_URL", "")
    if not url:
        return "unset → local SQLite"
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.hostname}{p.path}" if p.hostname else url
    except ValueError:
        return "<unparseable>"


if __name__ == "__main__":
    sys.exit(main())
