"""
app/api/webhooks.py
───────────────────
Inbound WhatsApp (Twilio). Only messages that (1) carry a valid Twilio
signature and (2) come from a phone registered to a workspace member are
acted on. Retried deliveries are no-ops (unique MessageSid).

Commands (case-insensitive):
  status         -> the `status` agent, answered in the webhook reply
  ask <question> -> `memory_qa`; with an LLM configured it runs after the
                    webhook returns and the answer is sent to the member
                    (Twilio expects a reply within ~15 s)
  anything else  -> help text

Replies go only to the member who wrote — internal, so no approval is needed.
Messages to anyone else are EXTERNAL tools and go through the approval inbox.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, session_factory
from app.kernel.agents import llm
from app.kernel.agents.runtime import run_agent
from app.kernel.channels import whatsapp
from app.kernel.models import ChannelMessage, Membership, User
from app.kernel.rbac import role_has
from app.kernel.schemas import normalize_phone
from app.kernel.tenancy import Principal

router = APIRouter()
logger = logging.getLogger("api.webhooks")

HELP = ("Company OS commands:\n"
        "• status — approvals waiting, overdue tasks, decisions to revisit\n"
        "• ask <question> — answer from company documents, with sources")


def _xml(text: str | None) -> Response:
    body = whatsapp.twiml_message(text) if text else '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=body, media_type="application/xml")


def _answer_later(principal: Principal, question: str, to_digits: str) -> None:
    db = session_factory()()
    try:
        run = run_agent(db, principal, "memory_qa", question, channel="whatsapp")
        reply = run.output or f"Sorry — I couldn't answer ({run.status}: {run.error})."
        db.commit()
        try:
            sid = whatsapp.send(to_digits, reply)
            db.add(ChannelMessage(workspace_id=principal.workspace_id, channel="whatsapp", direction="out",
                                  external_id=sid or None, from_addr="company", to_addr=to_digits, body=reply,
                                  user_id=principal.user_id))
            db.commit()
        except (whatsapp.ChannelNotConfigured, whatsapp.ChannelSendError):
            logger.exception("could not deliver WhatsApp answer for run %s", run.id)
    finally:
        db.close()


@router.post("/webhooks/whatsapp")
async def whatsapp_inbound(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    url = get_settings().public_base_url + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    if not whatsapp.valid_signature(url, params, request.headers.get("x-twilio-signature")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")

    sid = params.get("MessageSid") or params.get("SmsSid")
    try:
        phone = normalize_phone(params.get("From", ""))
    except ValueError:
        phone = None
    body = (params.get("Body") or "").strip()

    user = db.execute(select(User).where(User.phone == phone, User.is_active.is_(True))).scalar_one_or_none() if phone else None
    membership = None
    if user is not None:
        membership = db.execute(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id)).scalars().first()

    msg = ChannelMessage(
        workspace_id=membership.workspace_id if membership else None, channel="whatsapp", direction="in",
        external_id=sid, from_addr=phone or params.get("From", "")[:320], to_addr=params.get("To", "")[:320],
        body=body[:4000], user_id=user.id if membership else None,
    )
    db.add(msg)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()  # retried delivery of a message we already handled
        return _xml(None)

    if membership is None:
        db.commit()
        return _xml(None)  # unknown sender: record it, reveal nothing

    principal = Principal(user_id=user.id, workspace_id=membership.workspace_id, role=membership.role, user=user)
    if not role_has(principal.role, "agents.run"):
        db.commit()
        return _xml(f"Your role ({principal.role}) can't run agents from WhatsApp.")
    command, _, rest = body.partition(" ")
    command = command.lower()

    if command == "status":
        run = run_agent(db, principal, "status", "", channel="whatsapp")
        db.commit()
        return _xml(run.output or run.error)
    if command == "ask" and rest.strip():
        if llm.is_available():
            db.commit()
            background.add_task(_answer_later, principal, rest.strip(), phone)
            return _xml("Looking that up in the company documents — I'll reply shortly.")
        run = run_agent(db, principal, "memory_qa", rest.strip(), channel="whatsapp")
        db.commit()
        return _xml(run.output or run.error)
    db.commit()
    return _xml(HELP)
