# Quarantined `execution/` scripts

Moved here 2026-07-08 (Sprint 1.5 of the hardening pass). **Do not run these.**

All five were written against an *abandoned* copy of this project (the nested
`restaurant-agent/backend` tree, async SQLAlchemy) and reference tables the live
schema does not have — `bookings` and `payments`. The live schema uses
`reservations` and stores payment state on `orders` (`is_paid`,
`mpesa_checkout_request_id`, `mpesa_receipt`).

They are landmines rather than tools: each issues raw `DELETE FROM bookings` /
`DELETE FROM payments` against whatever `DATABASE_URL` is configured. Against the
live DB they'd either error out on a missing table or — if a future migration ever
introduces those names — silently delete real rows.

| script | what it claimed to do | why it's dead |
|---|---|---|
| `chaos_harness.py` | concurrency race harness for double-booking | `DELETE FROM bookings`; async engine |
| `debug_settle.py` | poke the payment settlement path | `INSERT/DELETE payments`, `bookings` |
| `verify_payment_callback.py` | verify M-Pesa callback settles | same |
| `verify_payment_trigger.py` | verify STK push creates pending payment | same |
| `verify_tools.py` | exercise LLM tool-calling | `DELETE FROM bookings` |

The live equivalents that actually run against the real schema:

- M-Pesa callback → `backend/tests/test_mpesa_webhook.py`
- Reservation double-booking race → `backend/tests/test_reservation_booking.py`
- LLM tool-calling → `backend/tests/test_orchestrator_metering.py`

If you want a real concurrency harness, write it against `backend/models.py` and
the `orders`/`reservations` tables — don't resurrect these.
