import os
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException
import logging

# Configure logging
logger = logging.getLogger("uvicorn")

router = APIRouter(
    prefix="/api/v1/webhooks",
    tags=["webhooks"],
)

# Webhook secrets from environment
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
MPESA_WEBHOOK_SECRET = os.getenv("MPESA_WEBHOOK_SECRET", "")

@router.post("/stripe")
async def stripe_webhook(request: Request):
    # Get the webhook payload and signature
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        logger.warning("Missing Stripe-Signature header")
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured")
        # In production, you might want to fail closed, but for dev we'll allow it
        logger.info("Processing Stripe webhook without verification (development mode)")
    else:
        try:
            import stripe
            # Verify the webhook signature
            stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            # Invalid payload
            logger.error(f"Invalid Stripe webhook payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error(f"Invalid Stripe webhook signature: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info(f"Received Stripe webhook: {len(payload)} bytes")
    # Process webhook logic here
    return {"status": "received"}

@router.post("/mpesa")
async def mpesa_webhook(request: Request):
    # Get the webhook payload
    payload = await request.body()

    # For M-Pesa, we'll do basic validation if secret is provided
    # Note: M-Pesa webhook validation varies by implementation
    # This is a basic HMAC-SHA256 validation - adjust as needed for your specific M-Pesa setup
    if MPESA_WEBHOOK_SECRET:
        # Get the signature from headers (adjust header name as needed for your M-Pesa implementation)
        # Common header names: X-Mpesa-Signature, X-Signature, etc.
        signature = request.headers.get("X-Mpesa-Signature") or request.headers.get("X-Signature")

        if not signature:
            logger.warning("Missing M-Pesa signature header")
            # For now, we'll allow it in development but log the warning
            logger.info("Processing M-Pesa webhook without verification (development mode)")
        else:
            # Verify the signature using HMAC-SHA256
            expected_signature = hmac.new(
                MPESA_WEBHOOK_SECRET.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()

            # Compare signatures securely
            if not hmac.compare_digest(expected_signature, signature):
                logger.error("Invalid M-Pesa webhook signature")
                raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        # Try to parse as JSON for logging
        payload_json = await request.json()
        logger.info(f"Received M-Pesa webhook: {payload_json}")
    except:
        # If not JSON, log as string
        logger.info(f"Received M-Pesa webhook: {payload.decode('utf-8', errors='ignore')[:200]}")

    # Process webhook logic here
    return {"status": "received"}
