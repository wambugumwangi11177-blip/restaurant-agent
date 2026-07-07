"""
execution/verify_tools.py
──────────────────────────
Directive: 005_database.md — Step B verification
Tests all three Step B tools directly against the live Neon database
without going through the LLM. This proves the service layer is correct
before wiring it to Groq.

Tests:
  1. check_availability — should find our 3 seeded tables for a small party
  2. create_booking     — should succeed on first call, reject on second (idempotency)
  3. get_menu_recommendations — should return our 3 seeded items

Usage:
    python execution/verify_tools.py

Requirements:
    pip install sqlalchemy asyncpg python-dotenv
"""

import asyncio
import hashlib
import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_script_dir  = os.path.dirname(os.path.abspath(__file__))
_root_dir    = os.path.dirname(_script_dir)
_nested_dir  = os.path.join(_root_dir, "restaurant-agent")
_backend_dir = os.path.join(_nested_dir, "backend")

sys.path.insert(0, _backend_dir)

# ── Load .env ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
for _p in [
    os.path.join(_nested_dir, ".env"),
    os.path.join(_root_dir, ".env"),
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        print(f"[INFO] Loaded env from: {_p}")
        break

# ── Build async DATABASE_URL (asyncpg format) ─────────────────────────────────
_db_url = os.getenv("DATABASE_URL", "")
if not _db_url:
    print("[ERROR] DATABASE_URL not set. Aborting.")
    sys.exit(1)

# Ensure asyncpg driver is used
if "postgresql+asyncpg" not in _db_url:
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://")
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://")

# asyncpg does NOT accept ?sslmode=require as a URL query param.
# Strip it from the URL and pass SSL config via connect_args instead.
_is_neon = "neon.tech" in _db_url
if "sslmode" in _db_url:
    import re
    _db_url = re.sub(r"[?&]sslmode=[^&]*", "", _db_url).rstrip("?&")

# SSL connect_args for asyncpg (required for Neon)
_connect_args = {"ssl": "require"} if _is_neon else {}

# ── Build async engine + session ──────────────────────────────────────────────
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(_db_url, echo=False, pool_pre_ping=True, connect_args=_connect_args)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Import the tools we are testing ──────────────────────────────────────────
# Import directly from the nested project path
sys.path.insert(0, os.path.join(_backend_dir, "app", "core"))

# We import the functions directly (not via TOOL_MAP) to test them in isolation
from tools import check_availability, create_booking, get_menu_recommendations


# ══════════════════════════════════════════════════════════════════════════════
# TEST RUNNER
# ══════════════════════════════════════════════════════════════════════════════

PASS  = "[PASS]"
FAIL  = "[FAIL]"
ERROR = "[ERROR]"

results: list[tuple[str, str, str]] = []  # (test_name, status, detail)


async def run_all_tests():
    async with AsyncSessionLocal() as db:

        # ── TEST 1: check_availability — happy path ───────────────────────────
        print("\n--- TEST 1: check_availability (happy path) ---")
        r1 = await check_availability(db, date="2026-12-25", time="19:00", guests=2)
        print(f"  Result: {r1}")
        if r1.startswith("SUCCESS"):
            results.append(("check_availability (2 guests)", PASS, r1[:80]))
        else:
            results.append(("check_availability (2 guests)", FAIL, r1[:80]))

        # ── TEST 2: check_availability — too many guests ──────────────────────
        print("\n--- TEST 2: check_availability (21 guests, should fail validation) ---")
        r2 = await check_availability(db, date="2026-12-25", time="19:00", guests=21)
        print(f"  Result: {r2}")
        if r2.startswith("FAILURE") and "1 and 20" in r2:
            results.append(("check_availability (21 guests validation)", PASS, r2[:80]))
        else:
            results.append(("check_availability (21 guests validation)", FAIL, r2[:80]))

        # ── TEST 3: create_booking — first call (should succeed) ──────────────
        print("\n--- TEST 3: create_booking (first call, should succeed) ---")
        test_hash = hashlib.sha256(b"test_phone_number_verify_tools").hexdigest()
        r3 = await create_booking(
            db,
            user_id_hash=test_hash,
            table_id=1,           # T1 from seed
            date="2026-12-25",
            time="19:00",
            guests=2,
        )
        print(f"  Result: {r3}")
        if r3.startswith("SUCCESS"):
            results.append(("create_booking (first call)", PASS, r3[:80]))
        else:
            results.append(("create_booking (first call)", FAIL, r3[:80]))

        # ── TEST 4: create_booking — second call same args (idempotency check) ─
        print("\n--- TEST 4: create_booking (DUPLICATE — idempotency must reject) ---")
        r4 = await create_booking(
            db,
            user_id_hash=test_hash,
            table_id=1,
            date="2026-12-25",
            time="19:00",
            guests=2,
        )
        print(f"  Result: {r4}")
        # Accept both ERROR (idempotency_key UniqueViolation) and FAILURE
        # (conflict pre-check caught the booked slot first). Both are correct.
        if r4.startswith("ERROR") or r4.startswith("FAILURE"):
            results.append(("create_booking (duplicate rejected)", PASS, r4[:80]))
        else:
            results.append(("create_booking (duplicate rejected)", FAIL, r4[:80]))

    # ── Tests 5/6 use a fresh session — avoids any aborted txn state ────────
    async with AsyncSessionLocal() as db2:
        # ── TEST 5: get_menu_recommendations — full menu ──────────────────────
        print("\n--- TEST 5: get_menu_recommendations (full menu) ---")
        r5 = await get_menu_recommendations(db2)
        print(f"  Result: {r5[:200]}")
        if r5.startswith("SUCCESS") and "Nyama Choma" in r5:
            results.append(("get_menu_recommendations (seeded items present)", PASS, r5[:80]))
        else:
            results.append(("get_menu_recommendations (seeded items present)", FAIL, r5[:80]))

        # ── TEST 6: get_menu_recommendations — with dietary note ──────────────
        print("\n--- TEST 6: get_menu_recommendations (with dietary restriction) ---")
        r6 = await get_menu_recommendations(db2, dietary_restrictions="vegetarian")
        print(f"  Result: {r6[:200]}")
        if r6.startswith("SUCCESS") and "vegetarian" in r6:
            results.append(("get_menu_recommendations (dietary note passed through)", PASS, r6[:80]))
        else:
            results.append(("get_menu_recommendations (dietary note passed through)", FAIL, r6[:80]))

    # ── Clean up test booking from DB ─────────────────────────────────────────
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "DELETE FROM bookings WHERE user_id_hash = :h"
        ), {"h": test_hash})
        await db.commit()
    print("\n[INFO] Test booking cleaned up from DB.")


async def main():
    print("=" * 60)
    print("  STEP B TOOL VERIFICATION")
    print("=" * 60)

    try:
        await run_all_tests()
    except Exception as e:
        print(f"\n[FATAL] Test runner crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()

    # ── Results summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    passed  = sum(1 for _, s, _ in results if s == PASS)
    failed  = sum(1 for _, s, _ in results if s != PASS)
    for name, status, detail in results:
        print(f"  {status}  {name}")
        if status != PASS:
            print(f"         Detail: {detail}")

    print(f"\n  {passed}/{len(results)} tests passed.")
    if failed:
        print("  Some tests FAILED — check details above.")
        sys.exit(1)
    else:
        print("  All tests passed. Step B tools are wired correctly.")


if __name__ == "__main__":
    asyncio.run(main())
