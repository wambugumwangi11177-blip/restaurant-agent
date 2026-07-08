"""
execution/debug_settle.py
─────────────────────────
Runs the settle_payment method directly to capture any database or SQL exceptions.
"""

import asyncio
import os
import sys
import re

# ── Path setup ────────────────────────────────────────────────────────────────
_script_dir  = os.path.dirname(os.path.abspath(__file__))
_root_dir    = os.path.dirname(_script_dir)
_nested_dir  = os.path.join(_root_dir, "restaurant-agent")
_backend_dir = os.path.join(_nested_dir, "backend")

sys.path.insert(0, _backend_dir)
sys.path.insert(0, _nested_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(_nested_dir, ".env"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

_db_url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://").replace("postgres://", "postgresql+asyncpg://")
if "neon.tech" in _db_url and "sslmode" not in _db_url:
    _db_url = re.sub(r"[?&]sslmode=[^&]*", "", _db_url).rstrip("?&")
_connect_args = {"ssl": "require"} if "neon.tech" in _db_url else {}

engine = create_async_engine(_db_url, echo=True, pool_pre_ping=True, connect_args=_connect_args)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def main():
    from app.services.payment_settlement import PaymentSettlementService
    
    # Let's seed a test row first
    from sqlalchemy import text
    booking_id = None
    checkout_id = "DEBUG_CHECKOUT_111"
    
    async with AsyncSessionLocal() as db:
        # Clean previous payment tests if any
        await db.execute(text("DELETE FROM payments WHERE checkout_request_id = :id"), {"id": checkout_id})
        
        # Insert test booking
        res = await db.execute(text("""
            INSERT INTO bookings (
                user_id_hash,
                table_id,
                booking_time,
                party_size,
                idempotency_key,
                payment_status
            )
            VALUES (
                'debug_callback_hash_111',
                1,
                '2026-12-25 19:00:00+03',
                2,
                'debug_callback_idempotency_111',
                'Unpaid'
            )
            ON CONFLICT (idempotency_key) DO UPDATE
            SET payment_status = 'Unpaid'
            RETURNING booking_id;
        """))
        booking_id = str(res.scalar())
        
        # Insert pending payment
        await db.execute(text("""
            INSERT INTO payments (
                booking_id,
                checkout_request_id,
                amount_cents,
                status
            )
            VALUES (
                :booking_id,
                :checkout_id,
                50000,
                'Pending'
            )
        """), {"booking_id": booking_id, "checkout_id": checkout_id})
        await db.commit()
        
        print(f"[SETUP] Dummy data created: booking={booking_id}, checkout={checkout_id}")

    # Now execute the settlement directly
    async with AsyncSessionLocal() as db:
        service = PaymentSettlementService(db)
        print("\n--- Running settle_payment ---")
        res = await service.settle_payment(
            checkout_id=checkout_id,
            result_code=0,
            raw_payload={"ResultCode": 0, "CheckoutRequestID": checkout_id}
        )
        print(f"Result: {res}")
        
    # Query final status
    async with AsyncSessionLocal() as db:
        res_pay = await db.execute(text("SELECT status FROM payments WHERE checkout_request_id = :id"), {"id": checkout_id})
        print(f"Final payment status: {res_pay.scalar()}")
        res_book = await db.execute(text("SELECT payment_status FROM bookings WHERE booking_id = :id"), {"id": booking_id})
        print(f"Final booking status: {res_book.scalar()}")
        
        # Clean up
        await db.execute(text("DELETE FROM payments WHERE booking_id = :b"), {"b": booking_id})
        await db.execute(text("DELETE FROM bookings WHERE booking_id = :b"), {"b": booking_id})
        await db.commit()

if __name__ == "__main__":
    asyncio.run(main())
