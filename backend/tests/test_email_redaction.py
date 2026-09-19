"""
Single-use auth tokens must never reach the application log.

When SMTP is unconfigured, email_utils falls back to logging the message so the
flow stays testable in development. The message body carries password-reset and
email-verification links, and those tokens are live credentials — anyone with
log access could complete the reset. send_email() redacts them; this pins that
behaviour, because the fallback is easy to "simplify" back into logging the raw
body.
"""
from __future__ import annotations

import logging

import pytest

import email_utils
from routers import auth as auth_router


@pytest.fixture
def unconfigured_smtp(monkeypatch):
    monkeypatch.setattr(email_utils, "_SMTP_CONFIGURED", False)


def _send_and_capture(caplog, body: str) -> str:
    caplog.set_level(logging.DEBUG)
    email_utils.send_email("owner@example.com", "Reset your password", body)
    return "\n".join(r.getMessage() for r in caplog.records)


def test_reset_token_is_redacted(unconfigured_smtp, caplog):
    logged = _send_and_capture(
        caplog,
        "Reset your password here:\nhttps://app.example.com/reset-password?token=SUPERSECRET123\n",
    )
    assert "SUPERSECRET123" not in logged
    assert "token=[REDACTED]" in logged


def test_verification_token_is_redacted(unconfigured_smtp, caplog):
    logged = _send_and_capture(
        caplog,
        "Verify your email address here:\nhttps://app.example.com/verify-email?token=VERIFYME456\n",
    )
    assert "VERIFYME456" not in logged


def test_token_with_trailing_query_params_is_redacted(unconfigured_smtp, caplog):
    logged = _send_and_capture(
        caplog, "https://app.example.com/reset-password?token=ABC123&lang=en\n"
    )
    assert "ABC123" not in logged
    # Only the token is removed; the rest of the URL stays useful for debugging.
    assert "lang=en" in logged


def test_the_links_auth_actually_sends_use_the_redacted_query_form(unconfigured_smtp, caplog):
    """
    The redaction keys on `token=`. If a link were ever changed to a path
    segment (/reset-password/<token>) the regex would silently stop matching,
    so pin the shape routers/auth.py actually builds.
    """
    import inspect

    source = inspect.getsource(auth_router)
    assert "/reset-password?token=" in source
    assert "/verify-email?token=" in source
