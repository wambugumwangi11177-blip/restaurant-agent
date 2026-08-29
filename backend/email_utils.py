"""
backend/email_utils.py
────────────────────────
Minimal SMTP sender for auth emails (password reset, email verification).
Generic SMTP rather than a specific vendor SDK — no new paid account is
required to stand this up. Matches this project's existing "best-effort side
channel, no-op + log when unconfigured" pattern (see ai/notify.py's VAPID
handling, ai/whatsapp/twilio_client.py's send()): set SMTP_HOST/SMTP_USER/
SMTP_PASSWORD/SMTP_FROM to enable real delivery. Unconfigured = the link is
logged instead of emailed, so auth flows are fully testable/usable in local
dev without any provider set up.
"""

import logging
import os
import re
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("email_utils")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER

_SMTP_CONFIGURED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)
if not _SMTP_CONFIGURED:
    logger.warning(
        "[email] SMTP not configured — password reset / verification emails "
        "will be logged instead of sent. Set SMTP_HOST/SMTP_USER/"
        "SMTP_PASSWORD/SMTP_FROM to enable delivery."
    )


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Best-effort send; never raises (a caller's request — e.g. registration,
    a password-reset request — must not fail because the mail server hiccuped).
    Returns True only if the message was actually handed to an SMTP server.
    """
    if not _SMTP_CONFIGURED:
        # The body carries raw single-use auth tokens (reset/verify links) —
        # anyone with log access could use them to take over the account.
        redacted = re.sub(r"(token=)[^\s&'\"]+", r"\1[REDACTED]", body)
        logger.info("[email] (SMTP not configured) to=%s subject=%r body=%r", to, subject, redacted)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("[email] send failed to=%s subject=%r", to, subject)
        return False
