"""
app/kernel/channels/email.py
────────────────────────────
Outbound email over SMTP with STARTTLS. Used only by the EXTERNAL `send_email`
tool, i.e. only after a human approved the exact message.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings
from app.kernel.channels.whatsapp import ChannelNotConfigured, ChannelSendError


def send(to: str, subject: str, body: str) -> str:
    s = get_settings()
    if not s.smtp_configured:
        raise ChannelNotConfigured("SMTP is not configured (SMTP_HOST/SMTP_FROM)")
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise ChannelSendError(f"SMTP send failed: {e}") from e
    return msg.get("Message-ID", "") or ""
