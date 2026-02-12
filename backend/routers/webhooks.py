from fastapi import APIRouter, Request, HTTPException
import logging

# Configure logging
logger = logging.getLogger("uvicorn")

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)

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

@router.post("/mpesa")
async def mpesa_webhook(request: Request):
    try:
        payload = await request.json()
        logger.info(f"Received M-Pesa webhook: {payload}")
        # Process webhook logic here
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing M-Pesa webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook")
