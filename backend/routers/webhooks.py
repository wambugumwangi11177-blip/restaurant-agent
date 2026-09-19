from fastapi import APIRouter, Request, HTTPException, Depends, Header
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape
import hmac
import logging
import os

from database import get_db
from integration.ingest import ingest
from rate_limit import limiter
import models
from phone_utils import normalize_phone
from ai.whatsapp import twilio_client, brain

# Configure logging
logger = logging.getLogger("uvicorn")

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


def _resolve_restaurant_by_phone(db: Session, from_number: str) -> models.Restaurant | None:
    """
    Reverse-lookup the restaurant whose owner sent an inbound WhatsApp message.
    Prefers a direct column query (Restaurant.owner_phone); falls back to the
    legacy OWNER_PHONE_{id} / OWNER_PHONE env-var scan for any restaurant whose
    column isn't set yet (backward compatible during transition).
    """
    normalized = normalize_phone(from_number)

    match = db.query(models.Restaurant).filter(
        models.Restaurant.owner_phone == normalized
    ).first()
    if match:
        return match

    for restaurant in db.query(models.Restaurant).filter(
        models.Restaurant.owner_phone.is_(None)
    ).all():
        owner_phone = os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))
        if owner_phone and normalize_phone(owner_phone) == normalized:
            return restaurant
    return None


def _resolve_staff_by_phone(db: Session, from_number: str) -> models.StaffMember | None:
    """
    Third case in inbound resolution, alongside owner and customer (directive
    016): is this message from a roster StaffMember? Matches on normalized
    phone, same precedence style as _resolve_restaurant_by_phone. Only
    StaffMember rows with a phone set are candidates — most of the roster
    (see StaffMember.phone's nullable docstring in models.py) has no way to
    be reached this way at all, which is expected, not a bug.
    """
    normalized = normalize_phone(from_number)
    if not normalized:
        return None
    return db.query(models.StaffMember).filter(
        models.StaffMember.phone == normalized,
        models.StaffMember.is_active.is_(True),
    ).first()


def _resolve_restaurant_for_customer(db: Session, from_number: str) -> models.Restaurant | None:
    """
    Resolve which restaurant a diner is talking to, by their most recent order.
    Enables two-way customer replies (REORDER / rating) for non-owner senders.
    Matches on canonical phone form since orders store many formats.
    """
    from ai.whatsapp.optout import canonical, last9
    key = canonical(from_number)
    if not key:
        return None
    q = db.query(models.Order).filter(models.Order.customer_phone != "")
    suf = last9(from_number)
    if suf:
        # Narrow to this customer by subscriber digits so resolution doesn't
        # depend on the order being among the N globally-most-recent.
        q = q.filter(models.Order.customer_phone.like(f"%{suf}%"))
    for o in q.order_by(models.Order.created_at.desc()).limit(50).all():
        if canonical(o.customer_phone) == key:
            return db.query(models.Restaurant).filter(
                models.Restaurant.id == o.restaurant_id
            ).first()
    return None

@router.post("/stripe")
async def stripe_webhook(request: Request):
    """
    Disabled. Stripe is not a payment path in this system (M-Pesa is — see
    /mpesa above), and this endpoint never verified a `Stripe-Signature`. A
    signature-less webhook that returns 200 is a settlement-forgery vector the
    moment anyone wires order fulfilment to it, so it fails closed with 501.

    To enable: verify `stripe.Webhook.construct_event(payload, sig, secret)`
    against `STRIPE_WEBHOOK_SECRET` BEFORE reading the body or acting on it —
    mirror the origin-check-first pattern in `_handle_mpesa_callback`.
    """
    raise HTTPException(status_code=501, detail="Stripe webhook not implemented")

_MPESA_ACK = {"ResultCode": 0, "ResultDesc": "Confirmation received successfully"}


def _extract_stk_metadata(items: list[dict]) -> dict:
    values = {item.get("Name"): item.get("Value") for item in items}
    return {
        "amount_cents": int(round(float(values.get("Amount", 0)) * 100)),
        "mpesa_receipt": str(values.get("MpesaReceiptNumber", "")),
        "phone_number": str(values.get("PhoneNumber", "")),
    }


def _verify_mpesa_token(supplied: str | None) -> None:
    """
    Origin check for the Daraja callback. Safaricom signs nothing and publishes
    no fixed source-IP range, so the only practical authentication is a secret
    embedded in the CallBackURL we register with them (`/webhooks/mpesa/{token}`)
    — Safaricom echoes it back on every callback; an attacker probing
    `/webhooks/mpesa` never sees it.

    This matters because the settlement path reads the paid amount from the
    request body (attacker-controlled), so the amount check below is trivially
    satisfied by a forger. Before this guard, anyone who obtained a
    CheckoutRequestID (logs, a leaked STK response, an insider) could POST a
    `ResultCode: 0` and flip an order to paid + fire the "payment confirmed"
    WhatsApp — free-order fraud.

    FAIL-CLOSED (CYB-103): the callback's only authentication is this token,
    so an unset or empty MPESA_CALLBACK_TOKEN means nothing can be verified —
    every callback is rejected with 403 and logged, regardless of whether
    M-Pesa credentials are configured. (The startup guard mirrors this:
    production refuses to boot without the token; dev logs a warning.)
    Once the token IS set, the legacy tokenless `/webhooks/mpesa` path 403s.
    """
    expected = os.getenv("MPESA_CALLBACK_TOKEN", "").strip()
    if not expected:
        # No token configured -> nothing to compare against -> reject (403)
        # with a loud log rather than trust an unauthenticated body.
        logger.error(
            "[MPesa Webhook] MPESA_CALLBACK_TOKEN is unset or empty — "
            "rejecting callback (fail closed). Set MPESA_CALLBACK_TOKEN to "
            "accept Daraja callbacks."
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    if supplied is None or not hmac.compare_digest(supplied, expected):
        logger.warning("[MPesa Webhook] Rejected callback with missing/incorrect URL token")
        raise HTTPException(status_code=403, detail="Forbidden")


def _settle_order_once(db: Session, order_id: int, receipt: str) -> bool:
    """
    Mark an order paid, exactly once, and report whether THIS caller was the one
    that did it. Returns False if it was already settled.

    The `WHERE is_paid = false` predicate is the whole point: it moves the
    decision into the database, where it is atomic. Safaricom retries callbacks
    aggressively, and the caller's earlier `if order.is_paid` check is a
    lock-free read — two retries landing together both pass it, both settle, and
    both emit ORDER_PAID, producing two "payment confirmed" WhatsApps to the
    customer and two audit rows. Here exactly one UPDATE reports rowcount == 1,
    and only that caller notifies.

    Works identically on SQLite and Postgres: no SELECT FOR UPDATE, no advisory
    lock, no dependence on the transaction isolation level.
    """
    rowcount = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.is_paid.is_(False))
        .update(
            {
                models.Order.is_paid: True,
                models.Order.payment_method: models.PaymentMethod.MPESA,
                models.Order.mpesa_receipt: receipt,
            },
            synchronize_session=False,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # uq_orders_mpesa_receipt (migration 029): this receipt is already
        # recorded against a DIFFERENT order — a duplicated/forged callback,
        # not a normal retry (a normal retry hits the `is_paid = false`
        # predicate above and rowcount == 0 before this is ever reached).
        # Never surface this as an error: Safaricom always gets its 200 ack.
        db.rollback()
        logger.warning(
            "[MPesa Webhook] Duplicate mpesa_receipt %s rejected for order %s "
            "— already settled against a different order.", receipt, order_id,
        )
        return False
    return rowcount == 1


@router.post("/mpesa")
@limiter.limit("30/minute")
async def mpesa_webhook_untokenized(request: Request, db: Session = Depends(get_db)):
    """Legacy tokenless path. 403s as soon as MPESA_CALLBACK_TOKEN is configured."""
    return await _handle_mpesa_callback(request, db, token=None)


@router.post("/mpesa/{token}")
@limiter.limit("30/minute")
async def mpesa_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    """Tokenized Daraja callback — this is the URL registered as CallBackURL."""
    return await _handle_mpesa_callback(request, db, token=token)


async def _handle_mpesa_callback(request: Request, db: Session, token: str | None):
    """
    Safaricom Daraja STK push result callback. Always acks with 200 + the
    Safaricom-expected body regardless of payment outcome — this endpoint's
    job is to acknowledge receipt of the callback, correlate it to an order,
    and hand off to the existing event bus; Safaricom will retry on non-200
    or on a body it doesn't recognize.

    Auth lives HERE, at the single choke point every callback route funnels
    through, not in each thin route body — so a new Daraja route (a C2B
    validation/confirmation URL, say) physically cannot reach settlement without
    passing the origin check, even if a future author forgets to add it. Verify
    before reading the body: an unauthenticated caller gets nothing.
    """
    _verify_mpesa_token(token)
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"[MPesa Webhook] Could not parse callback JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid callback payload")

    stk_callback = payload.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    result_code = stk_callback.get("ResultCode")

    if not checkout_request_id:
        logger.warning("[MPesa Webhook] Callback missing CheckoutRequestID - ignoring")
        return _MPESA_ACK

    order = db.query(models.Order).filter(
        models.Order.mpesa_checkout_request_id == checkout_request_id
    ).first()
    if not order:
        logger.warning(f"[MPesa Webhook] No order matched checkout_request_id={checkout_request_id}")
        return _MPESA_ACK

    # Idempotency: Safaricom may retry the same callback. Once an order is
    # marked paid, never re-process (would otherwise re-send the WhatsApp
    # receipt and duplicate the audit log entry).
    if order.is_paid:
        logger.info(f"[MPesa Webhook] Order {order.id} already paid - ignoring duplicate callback")
        return _MPESA_ACK

    if result_code != 0:
        logger.info(f"[MPesa Webhook] Payment failed for order {order.id}: {stk_callback.get('ResultDesc')}")
        from events.bus import emit, EventType
        emit(EventType.MPESA_PAYMENT_FAILED, {
            "restaurant_id": order.restaurant_id,
            "order_id": order.id,
            "reason": stk_callback.get("ResultDesc", ""),
        })
        return _MPESA_ACK

    items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
    meta = _extract_stk_metadata(items)

    # Amount verification. M-Pesa STK push settles in whole shillings, so a
    # genuine callback reports the whole-shilling floor of what we requested;
    # reject anything less than that. Without this check, a forged (or
    # underpaid) callback could mark an arbitrarily large order fully paid.
    expected_min_cents = (order.total or 0) // 100 * 100
    if meta["amount_cents"] < expected_min_cents:
        logger.error(
            f"[MPesa Webhook] Amount mismatch for order {order.id}: callback "
            f"{meta['amount_cents']} cents < expected >= {expected_min_cents} cents — NOT settling"
        )
        return _MPESA_ACK

    # Atomic settlement: mark paid, set method, and record the receipt in a
    # SINGLE transaction, so the 200 ACK we return to Safaricom can never lie
    # about settlement state. (Previously is_paid was set by the event handler
    # in a separate session/commit — if that swallowed an error, the ACK said
    # "success" to Safaricom while the order stayed unpaid, with no retry.)
    #
    # `_settle_order_once` is what makes this safe under concurrency, and it —
    # not the `if order.is_paid` read above — is the real idempotency guarantee.
    if not _settle_order_once(db, order.id, meta["mpesa_receipt"]):
        # Another callback won the race and has already notified. Ack and stop.
        logger.info(f"[MPesa Webhook] Order {order.id} settled concurrently - not re-notifying")
        return _MPESA_ACK

    # Notification + audit are pure side-effects — fire-and-forget so a slow
    # Twilio call never blocks the callback ACK, and a notification failure
    # can't undo an already-settled payment.
    from events.bus import emit_async, EventType
    emit_async(EventType.ORDER_PAID, {
        "restaurant_id": order.restaurant_id,
        "order_id": order.id,
        "amount_cents": meta["amount_cents"],
        "customer_phone": order.customer_phone or meta["phone_number"],
        "mpesa_reference": meta["mpesa_receipt"],
    })

    return _MPESA_ACK


def _verify_macsoft_key(supplied: str | None) -> None:
    """
    Origin check for the MacSoft data-push endpoint, same fail-closed shape as
    _verify_mpesa_token above: an unset MACSOFT_API_KEY means nothing can be
    compared against, so every request is rejected (401) rather than trusted.
    Uses hmac.compare_digest, not `==`, so response timing can't be used to
    brute-force the key byte-by-byte.
    """
    expected = os.getenv("MACSOFT_API_KEY", "").strip()
    if not expected:
        logger.error(
            "[MacSoft Webhook] MACSOFT_API_KEY is unset or empty — "
            "rejecting request (fail closed)."
        )
        raise HTTPException(status_code=401, detail="Unauthorized")
    if supplied is None or not hmac.compare_digest(supplied, expected):
        logger.warning("[MacSoft Webhook] Rejected request with missing/incorrect x-api-key")
        raise HTTPException(status_code=401, detail="Unauthorized")


# ─────────────────────────────────────────────────────────────────────────────
# MacSoft inbound data push
# ─────────────────────────────────────────────────────────────────────────────
#
# MacSoft is the client's POS/system of record. They refused direct database
# access, so the integration is a one-way push: MacSoft POSTs here, we mirror.
# Nothing is ever written back to MacSoft (integration/source_client.py has no
# write verb by construction).
#
# We deliberately do NOT validate against a fixed schema. MacSoft's export
# format has not been seen yet, and the owner's commitment to them is that we
# adapt to whatever they already emit rather than asking them to build anything
# custom. So this lands every record verbatim in the mirror (integration/
# ingest.py), which is an append-only staging area keyed on
# (source_system, entity, source_id, source_version). Mapping mirror rows onto
# orders/menu_items/inventory is a separate, later step, once a real payload has
# been inspected — that is exactly what the mirror layer is for.
#
# What this DOES guarantee today:
#   * Nothing accepted is lost — every record is committed before we return 200.
#   * Retries are free: the same (source_id, version) twice stores once.
#   * The raw payload is never written to the application log (PII).

MACSOFT_SOURCE_SLUG = "macsoft-prod"

# Keys we will accept as a record's stable identity, most explicit first. This
# list exists so MacSoft does not have to rename anything; extend it once their
# real field names are known.
_ID_KEYS = (
    "source_id", "id", "transaction_id", "txn_id", "invoice_no", "invoice_number",
    "receipt_no", "receipt_number", "sale_id", "order_id", "doc_no", "reference", "ref",
)
# Keys we will accept as a monotonic change signal.
_VERSION_KEYS = (
    "source_version", "version", "rowversion", "row_version", "revision",
    "updated_at", "modified_at", "modified_on", "last_modified", "changed_at",
)


def _macsoft_source_system(db: Session) -> int:
    """Row id for MacSoft in source_systems, created on first use."""
    from integration.models import SourceSystem
    row = db.query(SourceSystem).filter(SourceSystem.slug == MACSOFT_SOURCE_SLUG).first()
    if row is None:
        row = SourceSystem(
            slug=MACSOFT_SOURCE_SLUG,
            display_name="MacSoft (Vibanda Village)",
            mechanism="webhook",
            is_authoritative=1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row.id


def _first_present(record: dict, keys) -> str | None:
    """First key in `keys` present on `record` with a usable scalar value."""
    for k in keys:
        v = record.get(k)
        if v is None:
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    return None


def _identity(record: dict) -> tuple[str, str, bool]:
    """
    (source_id, source_version, derived) for one record.

    `derived` is True when we had to fall back to a content hash because the
    record carried no recognisable id or version. That still deduplicates exact
    repeats, but it cannot tell a correction from a resend — so it is surfaced
    in the response rather than hidden, and is the thing to fix once MacSoft's
    real field names are known.
    """
    from integration.ingest import payload_sha256
    digest = payload_sha256(record)
    source_id = _first_present(record, _ID_KEYS)
    version = _first_present(record, _VERSION_KEYS)
    derived = source_id is None or version is None
    return (source_id or f"sha256:{digest}", version or digest, derived)


def _records_from(payload) -> tuple[str, list[dict]]:
    """
    (entity, records) from whatever shape arrived.

    Accepts the documented envelope, a bare list, or a single bare object, so
    MacSoft can send their natural export without reshaping it.
    """
    if isinstance(payload, list):
        return ("unknown", [r for r in payload if isinstance(r, dict)])
    if not isinstance(payload, dict):
        return ("unknown", [])
    entity = str(payload.get("entity") or payload.get("type") or "unknown").strip() or "unknown"
    for key in ("records", "data", "items", "rows", "transactions", "sales"):
        block = payload.get(key)
        if isinstance(block, list):
            return (entity, [r for r in block if isinstance(r, dict)])
    # A single bare record.
    return (entity, [payload])


@router.post("/macsoft/data")
@limiter.limit("60/minute")
async def receive_macsoft_data(
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Inbound data push from MacSoft. See the block comment above for why this is
    schema-less and what it guarantees instead.
    """
    _verify_macsoft_key(x_api_key)

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"[MacSoft] Could not parse request JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    entity, records = _records_from(payload)
    if not records:
        # Explicit rather than a silent 200: an empty batch is almost always a
        # bug on the sending side, and a 200 would hide it.
        raise HTTPException(
            status_code=400,
            detail="No records found. Send a JSON object with a 'records' array, "
                   "a bare JSON array, or a single record object.",
        )
    if len(records) > 500:
        raise HTTPException(status_code=413, detail="Batch too large — send at most 500 records.")

    source_system_id = _macsoft_source_system(db)
    counts = {"inserted": 0, "superseded": 0, "skipped": 0}
    derived_identity = 0

    # One transaction for the whole batch, committed once at the end. A commit
    # per record is an fsync per record, and a 500-record push would then spend
    # most of the 60s gunicorn timeout waiting on the database. ingest() still
    # flushes each row, so dedupe inside a single batch works (SessionLocal is
    # autoflush=False, so the flush is what makes a repeated record visible to
    # the next lookup).
    try:
        for record in records:
            source_id, version, derived = _identity(record)
            if derived:
                derived_identity += 1
            action = ingest(
                db,
                source_system_id=source_system_id,
                entity=entity,
                source_id=source_id,
                source_version=version,
                payload=record,
                commit=False,
            )
            counts[action] = counts.get(action, 0) + 1
        db.commit()
    except Exception:
        # All-or-nothing: a partly-applied batch that still returned an error
        # would make MacSoft's retry ambiguous. Roll back and let them resend
        # the whole thing — that is free, because ingest is idempotent.
        db.rollback()
        logger.exception("[MacSoft] batch failed, rolled back (entity=%s, n=%d)", entity, len(records))
        raise HTTPException(status_code=500, detail="Could not store batch — please retry.")

    # Counts and shape only — never the payload itself. The records are already
    # durably stored in mirror_events; repeating them in the application log
    # would put customer names and phone numbers in plaintext where log
    # retention and erasure requests do not reach (Kenya DPA 2019).
    logger.info(
        "[MacSoft] entity=%s received=%d inserted=%d superseded=%d skipped=%d derived_identity=%d",
        entity, len(records), counts["inserted"], counts["superseded"],
        counts["skipped"], derived_identity,
    )

    return {
        "status": "stored",
        "entity": entity,
        "received": len(records),
        "inserted": counts["inserted"],
        "updated": counts["superseded"],
        "duplicates_ignored": counts["skipped"],
        # Surfaced so MacSoft can see we could not find an id/version on some
        # records and tell us the right field names.
        "records_without_id_or_version": derived_identity,
    }


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Inbound Twilio WhatsApp webhook — owner replies to the AI brain
    (SALES, STOCK, PENDING, TONIGHT, WINBACK, APPROVE n, REJECT n, HELP).
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("[WhatsApp Webhook] Missing X-Twilio-Signature header")
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    raw_body = await request.body()
    form = dict(parse_qsl(raw_body.decode("utf-8")))

    if not twilio_client.validate_twilio_request(str(request.url), form, signature):
        logger.warning("[WhatsApp Webhook] Invalid Twilio signature - rejecting")
        raise HTTPException(status_code=403, detail="Invalid request signature")

    from_number = form.get("From", "")
    body = form.get("Body", "")

    # Customer opt-out / opt-in is handled BEFORE owner resolution: a STOP comes
    # from a customer number that won't match any owner, and honouring it is a
    # legal obligation (AUP §04) that must work regardless of who sent it.
    from ai.whatsapp import optout as optout_mod
    if optout_mod.is_stop_keyword(body):
        optout_mod.record_opt_out(db, from_number, source="whatsapp_stop")
        reply = ("You have been unsubscribed and will no longer receive messages "
                 "from us. Reply START to resubscribe.")
        return PlainTextResponse(
            f"<Response><Message>{escape(reply)}</Message></Response>",
            media_type="application/xml",
        )
    if optout_mod.is_start_keyword(body):
        optout_mod.remove_opt_out(db, from_number)
        reply = "You are resubscribed. Reply STOP at any time to opt out."
        return PlainTextResponse(
            f"<Response><Message>{escape(reply)}</Message></Response>",
            media_type="application/xml",
        )

    # brain.handle_* calls below are wrapped: an exception here must still
    # produce a valid TwiML reply — Twilio expects XML back regardless, and an
    # unhandled 500 would surface as a broken delivery rather than a graceful
    # "something went wrong" reply (unlike the M-Pesa webhook path above,
    # which was already defensively coded end-to-end).
    restaurant = _resolve_restaurant_by_phone(db, from_number)
    if restaurant:
        try:
            reply_text = brain.handle_owner_command(db, restaurant.id, body)
        except Exception:
            logger.exception("[WhatsApp Webhook] handle_owner_command failed")
            reply_text = "Sorry, something went wrong processing that. Please try again."
        twiml = f"<Response><Message>{escape(reply_text)}</Message></Response>"
        return PlainTextResponse(twiml, media_type="application/xml")

    # Not the owner — is this a roster staff member (directive 016)? Checked
    # before customer resolution: a staff phone should never be misread as a
    # diner's just because it also appears somewhere in order history.
    staff_member = _resolve_staff_by_phone(db, from_number)
    if staff_member:
        try:
            reply_text = brain.handle_staff_command(db, staff_member, body)
        except Exception:
            logger.exception("[WhatsApp Webhook] handle_staff_command failed")
            reply_text = "Sorry, something went wrong processing that. Please try again."
        twiml = f"<Response><Message>{escape(reply_text)}</Message></Response>"
        return PlainTextResponse(twiml, media_type="application/xml")

    # Not staff either — try to resolve a diner by their order history so two-way
    # customer replies (REORDER, 1–5 rating from the receipt) work too.
    customer_restaurant = _resolve_restaurant_for_customer(db, from_number)
    if customer_restaurant:
        try:
            reply_text = brain.handle_customer_message(db, customer_restaurant.id, from_number, body)
        except Exception:
            logger.exception("[WhatsApp Webhook] handle_customer_message failed")
            reply_text = "Sorry, something went wrong processing that. Please try again."
        twiml = f"<Response><Message>{escape(reply_text)}</Message></Response>"
        return PlainTextResponse(twiml, media_type="application/xml")

    logger.warning("[WhatsApp Webhook] No restaurant matched for inbound sender")
    return PlainTextResponse("<Response></Response>", media_type="application/xml")
