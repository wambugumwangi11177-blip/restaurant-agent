"""Commit the authenticated envelope before parsing. No worker or paid service.

Source-row locks serialize mapping/replay across processes on PostgreSQL; unique
constraints are the final duplicate guard. Failed mappings roll back together,
while the independently committed envelope and safe attempt history survive.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from integration import quicksell as qs
from integration.ingest import ingest, payload_sha256
from integration.models import MirrorEvent
from integration.inbox_models import PosAppliedRecord, PosInbox, PosParseAttempt, PosSourceBinding
from time_utils import utcnow

PARSER_VERSION = "quicksell-envelope-v1"
MAX_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_NODES = 20_000


class MappingReviewError(ValueError):
    """Only fixed safe codes may be persisted; never provider-controlled text."""


def _revision_key(version: str):
    if version.isascii() and version.isdigit():
        return ("sequence", int(version))
    try:
        stamp = datetime.fromisoformat(version.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=qs.EAT)
        return ("time", stamp.astimezone(timezone.utc))
    except ValueError:
        return None


def _check_revision(db, row, sid, version):
    previous = db.query(PosAppliedRecord).filter_by(binding_id=row.binding_id,
                entity="sale", source_id=sid).order_by(PosAppliedRecord.id.desc()).first()
    if previous is None:
        raise MappingReviewError("legacy_revision_needs_review")
    prior, incoming = _revision_key(previous.source_version), _revision_key(version)
    if not prior or not incoming or prior[0] != incoming[0]:
        raise MappingReviewError("revision_order_unknown")
    return incoming[1] > prior[1]


def enabled() -> bool:
    # Staged, operator-controlled activation. Existing webhook stays available.
    return os.getenv("QUICKSELL_DURABLE_INBOX_ENABLED", "false").lower() == "true"


def decode_body(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Payload too large — maximum 1 MiB.")
    try:
        def reject_constant(value):
            raise ValueError("Non-finite JSON number")
        payload = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, "Invalid JSON payload")
    stack = [(payload, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise HTTPException(413, "JSON complexity limit exceeded.")
        if isinstance(value, dict):
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth + 1) for v in value)
    # Preserve the existing maximum batch contract, independently of mapping.
    _, records = qs.normalize_payload(payload)
    if len(records) > 500:
        raise HTTPException(413, "Batch too large — send at most 500 records.")
    return payload


async def read_body(request: Request) -> bytes:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Payload too large — maximum 1 MiB.")
    decode_body(bytes(raw))
    return bytes(raw)


def bind_source(db: Session, restaurant_id: int) -> PosSourceBinding:
    """Only called by authenticated delivery; GET never provisions anything."""
    binding = db.query(PosSourceBinding).filter_by(slug="quicksell").first()
    if binding:
        if binding.restaurant_id != restaurant_id:
            raise HTTPException(503, "POS source binding needs operator review.")
        return binding
    binding = PosSourceBinding(slug="quicksell", restaurant_id=restaurant_id)
    db.add(binding)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        binding = db.query(PosSourceBinding).filter_by(slug="quicksell").first()
        if binding is None or binding.restaurant_id != restaurant_id:
            raise HTTPException(503, "POS source binding needs operator review.")
    return binding


def store_receipt(db: Session, *, binding: PosSourceBinding, raw: bytes) -> str:
    receipt_id = str(uuid.uuid4())
    db.add(PosInbox(id=receipt_id, binding_id=binding.id,
                    restaurant_id=binding.restaurant_id, raw_body=raw.decode("utf-8"),
                    payload_sha256=hashlib.sha256(raw).hexdigest()))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(503, "Could not store batch — please retry.")
    return receipt_id


def _empty_result(entity: str, count: int) -> dict:
    return dict(status="stored", entity=entity, received=count, inserted=0, updated=0,
                duplicates_ignored=0, orders_inserted=0, orders_updated=0,
                nairobi_business_days=[], records_without_source_id=0,
                records_with_received_time_fallback=0, unmapped_records=0,
                stale_revisions_ignored=0)


def _has_source_time(record: dict) -> bool:
    raw = qs.first_present(record, qs._TIME_KEYS)
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


def _unambiguous_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            # Duplicate keys are syntactically JSON. Retain the original raw
            # envelope, but do not choose one interpretation for financial truth.
            raise MappingReviewError("ambiguous_json_keys")
        value[key] = item
    return value


def parse_receipt(db: Session, receipt_id: str, *, restaurant_id: int,
                  source_system_id: int, actor_id: int | None = None) -> dict:
    row = db.query(PosInbox).filter_by(id=receipt_id, restaurant_id=restaurant_id).first()
    if row is None:
        raise HTTPException(404, "Receipt not found")
    # Lock order is always source then receipt, including concurrent retries.
    db.query(PosSourceBinding).filter_by(id=row.binding_id).with_for_update().one()
    row = db.query(PosInbox).filter_by(id=receipt_id, restaurant_id=restaurant_id).with_for_update().populate_existing().one()
    if row.status == "parsed":
        result = dict(row.result)
        result.update(receipt_id=row.id, parse_status=row.status, already_parsed=True,
                      inserted=0, updated=0, orders_inserted=0, orders_updated=0,
                      duplicates_ignored=result["received"])
        db.rollback()  # release locks; a completed replay is read-only
        return result
    row.attempts += 1
    row.last_attempt_at = utcnow()
    row.parser_version = PARSER_VERSION
    try:
        # Savepoint keeps attempt metadata after mapping rollback. Envelope was
        # already committed by store_receipt in a separate transaction.
        with db.begin_nested():
            entity, records = qs.normalize_payload(json.loads(row.raw_body, object_pairs_hook=_unambiguous_object))
            result = _empty_result(entity, len(records))
            days = set()
            for record in records:
                sid, derived = qs.source_id_for(record)
                occurred = qs.parse_timestamp(record, row.received_at)
                version = qs.source_version_for(record, occurred)
                ent = str(record.get("entity") or record.get("type") or entity).strip() or entity
                if len(sid) > 128 or len(version) > 128 or len(ent) > 64:
                    raise ValueError("Identifier exceeds parser limit")
                mirror_entity = ent if ent != "unknown" else "envelope"
                prior = db.query(MirrorEvent).filter_by(source_system_id=source_system_id,
                    entity=mirror_entity, source_id=sid, source_version=version).first()
                if prior is not None and prior.payload_sha256 != payload_sha256(record):
                    raise MappingReviewError("identity_payload_conflict")
                result["records_without_source_id"] += int(derived)
                result["records_with_received_time_fallback"] += int(not _has_source_time(record))
                days.add(qs.nairobi_business_day(occurred))
                action = ingest(db, source_system_id=source_system_id, entity=mirror_entity,
                                source_id=sid, source_version=version, payload=record, commit=False)
                result[{"inserted": "inserted", "superseded": "updated", "skipped": "duplicates_ignored"}[action]] += 1
                if not qs.is_mappable_sale(record, ent):
                    result["unmapped_records"] += 1
                    continue
                applied = db.query(PosAppliedRecord.id).filter_by(binding_id=row.binding_id,
                            entity="sale", source_id=sid, source_version=version).first()
                if applied:
                    continue
                state = str(record.get("status") or "").lower()
                if state in ("void", "voided", "refund", "refunded", "cancelled", "canceled") or any(
                    record.get(key) for key in ("refunded", "voided", "is_refund", "is_void")
                ):
                    raise MappingReviewError("adjustment_needs_adapter")
                existing_order = qs._find_order(db, restaurant_id, sid)
                if existing_order is not None and action != "skipped":
                    if not _check_revision(db, row, sid, version):
                        result["stale_revisions_ignored"] += 1
                        continue
                # An earlier unknown shape may already be mirrored but never
                # mapped. Mirror deduplication must not prevent its first sale.
                mapping_action = action
                if action == "skipped" and existing_order is None:
                    mapping_action = "inserted"
                order_action = qs.maybe_apply_sale(db, restaurant_id=restaurant_id, entity=ent,
                                source_id=sid, ingest_action=mapping_action, record=record, occurred_at=occurred)
                db.add(PosAppliedRecord(binding_id=row.binding_id, inbox_id=row.id,
                                        entity="sale", source_id=sid, source_version=version))
                if order_action == "order_inserted":
                    result["orders_inserted"] += 1
                elif order_action == "order_updated":
                    result["orders_updated"] += 1
                db.flush()
            result["nairobi_business_days"] = sorted(days)
        row.status = ("unrecognized" if result["unmapped_records"] == len(records)
                      else "partial" if result["unmapped_records"] else "parsed")
        row.parsed_at = utcnow() if row.status == "parsed" else None
        row.error_code = None
        row.result = result
    except Exception as exc:
        # No payload, supplied identifier or exception text is exposed/logged.
        row.status = "failed"
        row.error_code = str(exc) if isinstance(exc, MappingReviewError) else "mapping_failed"
        row.result = _empty_result("unknown", 0)
    db.add(PosParseAttempt(inbox_id=row.id, actor_id=actor_id,
                          parser_version=PARSER_VERSION, outcome=row.status, error_code=row.error_code))
    db.commit()
    return dict(row.result, receipt_id=row.id, parse_status=row.status)
