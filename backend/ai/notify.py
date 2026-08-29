"""
backend/ai/notify.py
─────────────────────
Staff notification channel: in-app feed (always) + Web Push (best-effort).

This exists because the Twilio/WhatsApp channel (ai/whatsapp) needs a funded
Twilio account and, even when funded, only ever reached the restaurant
owner's phone (directives 015/016 flagged the missing per-staff routing as
a follow-up). This module is that follow-up, built as a channel independent
of Twilio entirely — costs nothing, needs no external account.

Two callers:
  - ai/orchestrator/push_notifier.py — event-bus subscriber, fans out to a
    role list per event type.
  - routers/support.py — notifies a specific user directly (ticket
    creator <-> OWNER/MANAGER), no role fan-out needed.

notify_user() always writes a Notification row (the in-app feed has no
dependency on push being configured or working) and then best-effort
dispatches Web Push to every subscribed device for that user. A push
failure never raises — same "best-effort side channel" posture as
ai/whatsapp/twilio_client.send().
"""

import os
import ipaddress
import json
import logging
import socket
from urllib.parse import urlparse

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("ai.notify")


def _endpoint_allowed(endpoint: str) -> bool:
    """True only for https push endpoints whose host resolves to a public IP.
    heuristic (a determined attacker could DNS-rebind between check and send)
    but closes the trivially-exploitable blind-POST-to-internal-services path."""
    try:
        parsed = urlparse(endpoint or "")
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        try:
            ip = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            infos = socket.getaddrinfo(parsed.hostname, None)
            ip = ipaddress.ip_address(infos[0][4][0])
        return ip.is_global
    except Exception:  # noqa: BLE001 — unresolvable/unparsable = not allowed
        return False

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL", "")

_VAPID_CONFIGURED = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_CLAIM_EMAIL)
if not _VAPID_CONFIGURED:
    logger.warning(
        "[notify] VAPID keys not configured — push notifications will no-op "
        "(the in-app feed still works). Set VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY/"
        "VAPID_CLAIM_EMAIL to enable background push."
    )


def notify_user(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    event_type: str,
    url: str | None = None,
    severity: str | None = None,
) -> models.Notification:
    """
    Write an in-app Notification row for user_id and best-effort push it to
    every device that user has subscribed. Returns the persisted row.
    Never raises — a push-delivery failure must not break the caller
    (mirrors send_whatsapp_message's best-effort contract).

    severity ("critical" | "high" | "medium" | None) opts this notification
    into the manager-escalation engine (ai/escalation/engine.py) — leave it
    None (the default) for ordinary operational notifications that shouldn't
    page anyone if left unread.
    """
    notif = models.Notification(
        user_id=user_id, title=title, body=body, event_type=event_type, url=url,
        severity=severity,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    _dispatch_push(db, user_id, title, body, url)
    return notif


def notify_users(
    db: Session,
    user_ids: list[int],
    title: str,
    body: str,
    event_type: str,
    url: str | None = None,
    severity: str | None = None,
) -> None:
    """Fan out notify_user() to several recipients (role-based alerts)."""
    for uid in user_ids:
        try:
            notify_user(db, uid, title, body, event_type, url, severity=severity)
        except Exception as exc:
            logger.error(f"[notify] Failed to notify user {uid}: {exc}")


def _dispatch_push(db: Session, user_id: int, title: str, body: str, url: str | None) -> None:
    if not _VAPID_CONFIGURED:
        return

    subs = db.query(models.PushSubscription).filter(
        models.PushSubscription.user_id == user_id
    ).all()
    if not subs:
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("[notify] pywebpush not installed — run: pip install pywebpush")
        return

    payload = json.dumps({"title": title, "body": body, "url": url or "/dashboard"})

    for sub in subs:
        # SSRF guard: subscription endpoints are client-registered URLs and
        # webpush() POSTs to them server-side. Without validation a malicious
        # authenticated user could point the backend at internal services
        # (cloud metadata, internal admin panels). Push endpoints from any
        # legitimate browser push service are https:// and public.
        if not _endpoint_allowed(sub.endpoint):
            logger.warning(
                "[notify] blocked push to disallowed endpoint for user %s", user_id,
            )
            continue
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{VAPID_CLAIM_EMAIL}"},
            )
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code in (404, 410):
                # Subscription is dead (browser unsubscribed, device reset,
                # etc.) — prune it so future sends don't keep retrying it.
                db.delete(sub)
                db.commit()
            else:
                logger.warning(f"[notify] Push send failed for user {user_id}: {exc}")
        except Exception as exc:
            logger.error(f"[notify] Unexpected push error for user {user_id}: {exc}")
