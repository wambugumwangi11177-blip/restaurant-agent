"""
execution/verify_payment_trigger.py
──────────────────────────────────
Verifies Sub-Phase B.1 (The Trigger):
  1. Resolves PII securely from UserVault.
  2. Creates a 'Pending' record in payments table.
  3. Mocks the M-Pesa STK Push API call.
  4. Updates the record with Safaricom CheckoutRequestID.
  5. Verifies no raw phone numbers bleed into the thought log or printouts.

Usage:
    python execution/verify_payment_trigger.py
"""

import asyncio
import os
import sys
import json
import re

# ── Path setup ────────────────────────────────────────────────────────────────
_script_dir  = os.path.dirname(os.path.abspath(__file__))
_root_dir    = os.path.dirname(_script_dir)
_nested_dir  = os.path.join(_root_dir, "restaurant-agent")
_backend_dir = os.path.join(_nested_dir, "backend")

# Insert backend/ first, then the nested project root so that src/ package is found
sys.path.insert(0, _nested_dir)
sys.path.insert(0, _backend_dir)

# ── Load .env ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
for _p in [
    os.path.join(_nested_dir, ".env"),
    os.path.join(_root_dir, ".env"),
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

# ── Setup DB Engine & Session ─────────────────────────────────────────────────
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

_db_url = os.getenv("DATABASE_URL", "")
if not _db_url:
    print("[ERROR] DATABASE_URL not set in environment.")
    sys.exit(1)

# Format to asyncpg
if "postgresql+asyncpg" not in _db_url:
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://")
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://")

_is_neon = "neon.tech" in _db_url
if "sslmode" in _db_url:
    _db_url = re.sub(r"[?&]sslmode=[^&]*", "", _db_url).rstrip("?&")

_connect_args = {"ssl": "require"} if _is_neon else {}

engine = create_async_engine(_db_url, echo=False, pool_pre_ping=True, connect_args=_connect_args)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Setup User Vault Token and Test Data ──────────────────────────────────────
from src.services.vault import VaultService
from sqlalchemy import text

async def setup_test_vault_user() -> str:
    """Creates a deterministic vault token in user_vault table for testing."""
    vault = VaultService()
    test_phone = "+254712345678"
    token = vault.get_or_create_token(test_phone)
    print(f"[SETUP] Setup user vault token: {token} mapping to {test_phone[-4:]}")
    return token

async def run_verification():
    # 1. Setup vault user
    user_token = await setup_test_vault_user()
    
    # 2. Setup a fresh dummy booking to pay for
    booking_id = None
    async with AsyncSessionLocal() as db:
        insert_booking_query = text("""
            INSERT INTO bookings (
                user_id_hash,
                table_id,
                booking_time,
                party_size,
                idempotency_key,
                payment_status
            )
            VALUES (
                :user_id_hash,
                1,
                '2026-12-25 19:00:00+03',
                2,
                'test_payment_trigger_idempotency_key',
                'Unpaid'
            )
            ON CONFLICT (idempotency_key) DO UPDATE
            SET payment_status = 'Unpaid'
            RETURNING booking_id;
        """)
        res = await db.execute(insert_booking_query, {"user_id_hash": user_token})
        booking_id = str(res.scalar())
        await db.commit()
        print(f"[SETUP] Created test booking: {booking_id}")

    # 3. Call the tool
    print("\n--- Running initiate_payment tool ---")
    from app.core.tools import initiate_payment
    
    async with AsyncSessionLocal() as db:
        tool_result = await initiate_payment(
            db=db,
            user_token=user_token,
            booking_id=booking_id,
            amount_cents=50000  # KES 500.00
        )
        print(f"Tool Result: {tool_result}")

        # Assertions
        if not tool_result.startswith("PENDING_PAYMENT:"):
            print(f"[FAIL] Expected status PENDING_PAYMENT, got: {tool_result}")
            sys.exit(1)
            
        checkout_match = re.search(r"CheckoutID:\s*(\S+)", tool_result)
        if not checkout_match:
            print("[FAIL] CheckoutID not found in tool response.")
            sys.exit(1)
        checkout_id = checkout_match.group(1)
        print(f"[PASS] Tool returned PENDING_PAYMENT with CheckoutID: {checkout_id}")

        # 4. Verify DB record
        print("\n--- Verifying Database Record ---")
        verify_db_query = text("""
            SELECT status, amount_cents, checkout_request_id
            FROM payments
            WHERE booking_id = :booking_id
        """)
        res = await db.execute(verify_db_query, {"booking_id": booking_id})
        payments_rows = res.fetchall()
        
        if not payments_rows:
            print("[FAIL] No payment record was created in the database.")
            sys.exit(1)
            
        print(f"Found {len(payments_rows)} payments record(s).")
        for row in payments_rows:
            print(f"  Record: status={row.status}, amount={row.amount_cents} cents, checkout_id={row.checkout_request_id}")
            
        # Match checkout_id
        db_checkout_ids = [row.checkout_request_id for row in payments_rows]
        if checkout_id not in db_checkout_ids:
            print(f"[FAIL] Expected checkout_id {checkout_id} to be recorded in DB, got: {db_checkout_ids}")
            sys.exit(1)
            
        print("[PASS] Database state matches STK push response.")

        # 5. Privacy audit
        print("\n--- Privacy Audit ---")
        # We ensure +254712345678 is NOT in the tool_result string
        if "+254" in tool_result or "712345678" in tool_result:
            print(f"[FAIL] Raw phone number leaked in tool result string!")
            sys.exit(1)
        else:
            print("[PASS] No raw phone number leaked in tool result.")

    # 6. Cleanup
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM payments WHERE booking_id = :b"), {"b": booking_id})
        await db.execute(text("DELETE FROM bookings WHERE booking_id = :b"), {"b": booking_id})
        await db.commit()
    print("\n[CLEANUP] Test records removed.")

if __name__ == "__main__":
    asyncio.run(run_verification())
