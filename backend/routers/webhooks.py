"""Inbound webhooks.

Only MacSoft remains. Stripe, M-Pesa and WhatsApp were retired in 6aee044
("retire external payment and phone integrations") and must stay gone —
tests/test_retired_integrations.py asserts those paths 404 and cannot settle
an order.

Why this file came back: 6aee044 deleted the 392-line pre-MacSoft version of
webhooks.py on its branch while master's copy had grown to 706 lines with the
MacSoft ingest and tracer endpoints (#11, efac96a, 3861e58, 43d4331). The
consolidation merge (48aa515) resolved that delete/modify conflict by taking
the delete, so master shipped with no way for MacSoft to deliver data at all —
the endpoint the production MACSOFT_API_KEY exists for — while keeping the 26
tests that prove it works. This restores the MacSoft half only.
"""
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
import hmac
import logging
import os

from database import get_db
from integration.ingest import ingest
from rate_limit import limiter
import models  # noqa: F401  (kept for parity with the rest of routers/)

logger = logging.getLogger("uvicorn")

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


def _verify_macsoft_key(supplied: str | None) -> None:
    """
    Origin check for the MacSoft data-push endpoint. Fail-closed: an unset
    MACSOFT_API_KEY means nothing can be compared against, so every request
    is rejected (401) rather than trusted.
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


@router.get("/macsoft/status")
@limiter.limit("60/minute")
async def macsoft_status(
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Prove the pipeline end to end, from outside.

    This is the tracer bullet for the MacSoft integration. Without it, the only
    way to confirm a push actually landed is to read Railway's logs — which
    MacSoft cannot do and the owner should not have to. "It returned 200" is
    not evidence: the endpoint returned 200 for weeks while storing nothing.

    Pair it with a push and the whole chain is verified in two calls that
    anyone with the key can make:

        POST /webhooks/macsoft/data   -> {"inserted": 1, ...}
        GET  /webhooks/macsoft/status -> total_records goes up by 1

    That single round trip exercises DNS, TLS, the API key, JSON parsing,
    identity extraction, the database write, and the read back. If the number
    moves, the integration works. If it does not, it does not — regardless of
    what any status code said.

    Read-only, and deliberately returns NO payload contents: counts and
    timestamps only. Someone holding the push key should be able to confirm
    delivery without being handed back the restaurant's transactions.
    """
    _verify_macsoft_key(x_api_key)

    from sqlalchemy import func as _func
    from integration.models import MirrorEvent, SourceSystem

    try:
        row = db.query(SourceSystem).filter(
            SourceSystem.slug == MACSOFT_SOURCE_SLUG).first()
        if row is None:
            # Nothing has ever been pushed. Not an error — the honest answer
            # before the first delivery, and what MacSoft should see while
            # they are still building.
            return {
                "status": "ready",
                "connected": False,
                "detail": "No data received yet. Push a record to "
                          "POST /webhooks/macsoft/data and call this again.",
                "total_records": 0,
                "by_entity": {},
                "last_received_at": None,
            }

        total = db.query(_func.count(MirrorEvent.id)).filter(
            MirrorEvent.source_system_id == row.id).scalar() or 0

        by_entity = {
            entity: int(count)
            for entity, count in db.query(
                MirrorEvent.entity, _func.count(MirrorEvent.id)
            ).filter(MirrorEvent.source_system_id == row.id)
             .group_by(MirrorEvent.entity).all()
        }

        # Split by what actually happened to each record, so a caller can tell
        # "you sent 500 and we stored 500" from "you sent 500 and 499 were
        # repeats" without reading a log.
        by_action = {
            action: int(count)
            for action, count in db.query(
                MirrorEvent.action, _func.count(MirrorEvent.id)
            ).filter(MirrorEvent.source_system_id == row.id)
             .group_by(MirrorEvent.action).all()
        }

        latest = db.query(MirrorEvent).filter(
            MirrorEvent.source_system_id == row.id
        ).order_by(MirrorEvent.id.desc()).first()

        return {
            "status": "ok",
            "connected": total > 0,
            "total_records": int(total),
            "by_entity": by_entity,
            "by_action": by_action,
            "last_received_at": latest.received_at.isoformat() + "Z" if latest else None,
            # The source_id is MacSoft's own identifier, echoed so they can
            # confirm WHICH record landed — not restaurant data.
            "last_source_id": latest.source_id if latest else None,
        }
    except Exception as exc:  # noqa: BLE001
        # A failure here means the mirror tables are unreachable — migration
        # 046 never applied, or the database is down. Say so plainly: a
        # silent 500 would look identical to "no data yet".
        logger.exception("[MacSoft] status check failed")
        raise HTTPException(
            status_code=503,
            detail=f"Storage unavailable — the integration cannot accept data: {type(exc).__name__}",
        )
