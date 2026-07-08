"""
execution/verify_payment_callback.py
───────────────────────────────────
Verifies Sub-Phase B.2 (The Secure Callback):
  1. Starts a local Uvicorn instance running our FastAPI backend main.py
  2. Creates a test booking + pending payment in Neon.
  3. Sends a mock callback POST request to the local webhook callback.
  4. Waits briefly for the background task to settle.
  5. Verifies database atomic update (Payment Completed AND Booking Paid).
  6. Validates Idempotency (sends callback again, verifies no collision or double-update).
  7. Shuts down the local server and cleans up test data.

Usage:
    python execution/verify_payment_callback.py
"""

import asyncio
import os
import sys
import httpx
import re
import socket
import subprocess
import time
from sqlalchemy import text

# ── Path setup ────────────────────────────────────────────────────────────────
_script_dir  = os.path.dirname(os.path.abspath(__file__))
_root_dir    = os.path.dirname(_script_dir)
_nested_dir  = os.path.join(_root_dir, "restaurant-agent")
_backend_dir = os.path.join(_nested_dir, "backend")

sys.path.insert(0, _backend_dir)
sys.path.insert(0, _nested_dir)

# ── Load env ──────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
for _p in [
    os.path.join(_nested_dir, ".env"),
    os.path.join(_root_dir, ".env"),
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

# ── DB setup ──────────────────────────────────────────────────────────────────
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

# We define a function to create the engine on demand to avoid socket inheritance issues
def get_async_session_maker():
    _engine = create_async_engine(_db_url, echo=False, pool_pre_ping=True, connect_args=_connect_args)
    return sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False), _engine

def get_free_port() -> int:
    """Finds a free port on localhost to start the server."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

async def check_db_state(booking_id: str, checkout_id: str) -> tuple[str, str]:
    """Queries current status of payment and booking."""
    session_maker, _engine = get_async_session_maker()
    async with session_maker() as db:
        res_pay = await db.execute(
            text("SELECT status FROM payments WHERE checkout_request_id = :id"),
            {"id": checkout_id}
        )
        pay_status = res_pay.scalar()

        res_book = await db.execute(
            text("SELECT payment_status FROM bookings WHERE booking_id = :id"),
            {"id": booking_id}
        )
        book_status = res_book.scalar()

    await _engine.dispose()
    return pay_status, book_status

async def main():
    print("=" * 60)
    print("  SUB-PHASE B.2 WEBHOOK CALLBACK VERIFICATION")
    print("=" * 60)

    # 1. Setup test data in DB: 1 Unpaid booking + 1 Pending payment
    booking_id = None
    checkout_id = "VERIFY_MOCK_CHECKOUT_999"
    
    session_maker, _engine = get_async_session_maker()
    async with session_maker() as db:
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
                'verify_callback_hash_999',
                1,
                '2026-12-25 19:00:00+03',
                2,
                'verify_callback_idempotency_999',
                'Unpaid'
            )
            ON CONFLICT (idempotency_key) DO UPDATE
            SET payment_status = 'Unpaid'
            RETURNING booking_id;
        """))
        booking_id = str(res.scalar())
        
        # Clean previous payment tests if any
        await db.execute(text("DELETE FROM payments WHERE checkout_request_id = :id"), {"id": checkout_id})
        
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

    # Dispose the engine completely so uvicorn subprocess doesn't inherit active sockets
    await _engine.dispose()

    # 2. Choose local port and start server in background
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[INFO] Starting local Uvicorn backend on port {port}...")

    # Start the server process using Python interpreter from PATH (will inherit current env with loaded vars)
    uvicorn_log_path = os.path.join(_script_dir, "uvicorn_verify.log")
    uvicorn_log = open(uvicorn_log_path, "w")
    
    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m", "uvicorn",
            "main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "debug"
        ],
        cwd=_backend_dir,
        stdout=uvicorn_log,
        stderr=uvicorn_log
    )

    # Wait for server to start responding
    time.sleep(3.0)

    print(f"[SETUP] Created test booking: {booking_id}")
    print(f"[SETUP] Created pending payment: {checkout_id}")


    # Check initial states
    pay_init, book_init = await check_db_state(booking_id, checkout_id)
    print(f"  Initial DB State: payments.status={pay_init}, bookings.payment_status={book_init}")
    if pay_init != "Pending" or book_init != "Unpaid":
        print("[FAIL] Initial state setup incorrect.")
        server_process.terminate()
        sys.exit(1)

    # Diagnostic DB check on the running server
    async with httpx.AsyncClient() as client:
        try:
            diag_res = await client.get(f"{base_url}/diagnostic_db_session", timeout=5.0)
            print(f"[DIAGNOSTIC] Server DB check: {diag_res.json()}")
        except Exception as e:
            print(f"[DIAGNOSTIC] Server DB check failed: {e}")

    # 3. Trigger Mock Callback POST request (ResultCode 0 - Success)
    print("\n--- Sending Mock Callback POST request (Success) ---")
    mock_payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": checkout_id,
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully."
            }
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/v1/payments/callback", json=mock_payload)
        print(f"Server Response Status: {response.status_code}")
        print(f"Server Response Body: {response.json()}")
        
        if response.status_code != 200:
            print("[FAIL] Webhook returned non-200 response status.")
            server_process.terminate()
            sys.exit(1)

    # 4. Wait for background task settlement
    print("[INFO] Waiting 2 seconds for background settlement service to process...")
    await asyncio.sleep(2.0)

    # Verify atomic update
    pay_after, book_after = await check_db_state(booking_id, checkout_id)
    print(f"  DB State after callback: payments.status={pay_after}, bookings.payment_status={book_after}")
    
    if pay_after != "Completed" or book_after != "Paid":
        print("[FAIL] Webhook did not update tables atomically to Completed / Paid.")
        server_process.terminate()
        sys.exit(1)
    print("[PASS] Atomic updates verified successfully.")

    # 5. Test Idempotency (Double post protection)
    print("\n--- Sending Duplicate Callback request (Idempotency Audit) ---")
    async with httpx.AsyncClient() as client:
        response_dup = await client.post(f"{base_url}/v1/payments/callback", json=mock_payload)
        print(f"Duplicate Response Status: {response_dup.status_code}")
        
    await asyncio.sleep(1.0)
    pay_dup, book_dup = await check_db_state(booking_id, checkout_id)
    print(f"  DB State after duplicate callback: payments.status={pay_dup}, bookings.payment_status={book_dup}")
    if pay_dup != "Completed" or book_dup != "Paid":
        print("[FAIL] Duplicate callback corrupted database states.")
        server_process.terminate()
        sys.exit(1)
    print("[PASS] Idempotency checks passed.")

    # 6. Cleanup
    session_maker, _engine = get_async_session_maker()
    async with session_maker() as db:
        await db.execute(text("DELETE FROM payments WHERE booking_id = :b"), {"b": booking_id})
        await db.execute(text("DELETE FROM bookings WHERE booking_id = :b"), {"b": booking_id})
        await db.commit()
    await _engine.dispose()
    print("\n[CLEANUP] Test data cleaned from Neon.")

    # Stop server
    server_process.terminate()
    server_process.wait()
    uvicorn_log.close()
    print("[INFO] Local server terminated.")
    
    # Read and show logs if failed
    if pay_after != "Completed" or book_after != "Paid":
        print("\n=== Uvicorn Server Logs ===")
        with open(uvicorn_log_path, "r") as f:
            print(f.read())
        print("==========================")
        sys.exit(1)
        
    # Clean up log file
    try:
        os.remove(uvicorn_log_path)
    except Exception:
        pass
    
    print("\n" + "=" * 60)
    print("  RESULTS: ALL WEBHOOK TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
