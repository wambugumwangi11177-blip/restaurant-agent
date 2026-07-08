from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape
import logging
import os

from database import get_db
import models
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
    normalized = from_number.replace("whatsapp:", "").strip()

    match = db.query(models.Restaurant).filter(
        models.Restaurant.owner_phone == normalized
    ).first()
    if match:
        return match

    for restaurant in db.query(models.Restaurant).filter(
        models.Restaurant.owner_phone.is_(None)
    ).all():
        owner_phone = os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))
        if owner_phone and owner_phone.replace("whatsapp:", "").strip() == normalized:
            return restaurant
    return None

@router.post("/stripe")
async def stripe_webhook(request: Request):
    try:
        payload = await request.body()
        logger.info(f"Received Stripe webhook: {len(payload)} bytes")
        # Process webhook logic here
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook")

_MPESA_ACK = {"ResultCode": 0, "ResultDesc": "Confirmation received successfully"}


def _extract_stk_metadata(items: list[dict]) -> dict:
    values = {item.get("Name"): item.get("Value") for item in items}
    return {
        "amount_cents": int(round(float(values.get("Amount", 0)) * 100)),
        "mpesa_receipt": str(values.get("MpesaReceiptNumber", "")),
        "phone_number": str(values.get("PhoneNumber", "")),
    }


@router.post("/mpesa")
async def mpesa_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Safaricom Daraja STK push result callback. Always acks with 200 + the
    Safaricom-expected body regardless of payment outcome — this endpoint's
    job is to acknowledge receipt of the callback, correlate it to an order,
    and hand off to the existing event bus; Safaricom will retry on non-200
    or on a body it doesn't recognize.
    """
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
    order.is_paid = True
    order.payment_method = models.PaymentMethod.MPESA
    order.mpesa_receipt = meta["mpesa_receipt"]
    db.commit()

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

    restaurant = _resolve_restaurant_by_phone(db, from_number)
    if not restaurant:
        logger.warning("[WhatsApp Webhook] No restaurant matched for inbound sender")
        return PlainTextResponse("<Response></Response>", media_type="application/xml")

    reply_text = brain.handle_owner_command(db, restaurant.id, body)

    twiml = f"<Response><Message>{escape(reply_text)}</Message></Response>"
    return PlainTextResponse(twiml, media_type="application/xml")
