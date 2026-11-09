"""Owner-scoped receipt metadata and controlled replay; never exposes raw POS PII."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
import auth
import models
from database import get_db
from integration import inbox
from integration.inbox_models import PosInbox, PosParseAttempt, PosSourceBinding
from routers.deps import get_restaurant_or_none
from rate_limit import limiter

router = APIRouter(prefix="/pos/quicksell", tags=["pos-evidence"])


class ReceiptOut(BaseModel):
    id: str
    received_at: datetime
    status: Literal["pending", "failed", "unrecognized", "partial", "parsed"]
    parser_version: str | None
    attempts: int
    last_attempt_at: datetime | None
    parsed_at: datetime | None
    error_code: str | None
    payload_sha256: str
    model_config = {"from_attributes": True}


class SourceStatusOut(BaseModel):
    durable_inbox_enabled: bool
    source_bound: bool
    receipts: int
    by_status: dict[str, int]
    last_receipt_at: datetime | None
    last_successful_parse_at: datetime | None
    backlog: int
    completeness: Literal["not_checked"]
    sales_live: None
    why: str
    legacy_receipts: str


class AttemptOut(BaseModel):
    id: int
    actor_id: int | None
    attempted_at: datetime
    parser_version: str
    outcome: str
    error_code: str | None


class ReplayOut(BaseModel):
    status: Literal["stored"]
    entity: str
    received: int
    inserted: int
    updated: int
    duplicates_ignored: int
    orders_inserted: int
    orders_updated: int
    nairobi_business_days: list[str]
    records_without_source_id: int
    records_with_received_time_fallback: int
    unmapped_records: int
    stale_revisions_ignored: int
    receipt_id: str
    parse_status: Literal["pending", "failed", "unrecognized", "partial", "parsed"]
    already_parsed: bool = False


def _restaurant(db, user):
    if getattr(user, "impersonated_by", None):
        raise HTTPException(403, "Use your own account for evidence review.")
    restaurant = get_restaurant_or_none(db, user)
    if restaurant is None:
        raise HTTPException(404, "Restaurant not configured")
    return restaurant


@router.get("/status", response_model=SourceStatusOut)
def status(db: Session = Depends(get_db),
           user: models.User = Depends(auth.require_role(models.Role.ADMIN))):
    restaurant = _restaurant(db, user)
    binding = db.query(PosSourceBinding).filter_by(restaurant_id=restaurant.id, slug="quicksell").first()
    query = db.query(PosInbox).filter_by(restaurant_id=restaurant.id)
    counts = dict(query.with_entities(PosInbox.status, func.count()).group_by(PosInbox.status).all())
    latest = query.with_entities(func.max(PosInbox.received_at)).scalar()
    parsed = query.with_entities(func.max(PosInbox.parsed_at)).scalar()
    return dict(durable_inbox_enabled=inbox.enabled(), source_bound=binding is not None,
                receipts=sum(counts.values()), by_status=counts,
                last_receipt_at=latest, last_successful_parse_at=parsed,
                backlog=sum(counts.get(s, 0) for s in ("pending", "failed", "unrecognized", "partial")),
                completeness="not_checked", sales_live=None,
                why="Receipt and parsing are separate milestones. Parsing alone does not establish complete sales coverage.",
                legacy_receipts="not_counted_in_this_inbox")


@router.get("/receipts", response_model=list[ReceiptOut])
def receipts(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000),
             state: Literal["pending", "failed", "unrecognized", "partial", "parsed"] | None = None,
             db: Session = Depends(get_db),
             user: models.User = Depends(auth.require_role(models.Role.ADMIN))):
    restaurant = _restaurant(db, user)
    query = db.query(PosInbox).filter_by(restaurant_id=restaurant.id)
    if state:
        query = query.filter_by(status=state)
    return query.order_by(PosInbox.received_at.desc(), PosInbox.id.desc()).offset(offset).limit(limit).all()


@router.get("/receipts/{receipt_id}/attempts", response_model=list[AttemptOut])
def attempts(receipt_id: str, db: Session = Depends(get_db),
             user: models.User = Depends(auth.require_role(models.Role.ADMIN))):
    restaurant = _restaurant(db, user)
    if not db.query(PosInbox.id).filter_by(id=receipt_id, restaurant_id=restaurant.id).first():
        raise HTTPException(404, "Receipt not found")
    rows = db.query(PosParseAttempt).filter_by(inbox_id=receipt_id).order_by(PosParseAttempt.id.desc()).limit(200).all()
    return [dict(id=r.id, actor_id=r.actor_id, attempted_at=r.attempted_at,
                 parser_version=r.parser_version, outcome=r.outcome, error_code=r.error_code) for r in rows]


@router.post("/receipts/{receipt_id}/replay", response_model=ReplayOut)
@limiter.limit("10/minute")
def replay(receipt_id: str, request: Request, db: Session = Depends(get_db),
           user: models.User = Depends(auth.require_role(models.Role.ADMIN))):
    restaurant = _restaurant(db, user)
    if not inbox.enabled():
        raise HTTPException(409, "Durable inbox replay is disabled.")
    from integration.models import SourceSystem
    source = db.query(SourceSystem).filter_by(slug="quicksell").first()
    if source is None:
        raise HTTPException(409, "Source is not configured.")
    try:
        return inbox.parse_receipt(db, receipt_id, restaurant_id=restaurant.id,
                                   source_system_id=source.id, actor_id=user.id)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "Replay unavailable — please retry.")
