"""Mirror + provenance tables for the client source-system integration.

Design rules:
  * Every mirrored row carries (source_system, source_id, source_version).
  * Rows are immutable: a correction is a new source_version, never an UPDATE.
  * Nothing in this module is ever written back to the client system.
"""
from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Integer, JSON, String, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SourceSystem(Base):
    """One row per connected client system. The trust anchor for everything else."""
    __tablename__ = "source_systems"
    id = Column(Integer, primary_key=True)
    slug = Column(String(64), nullable=False, unique=True)          # e.g. "client-pos-prod"
    display_name = Column(String(200), nullable=False)
    mechanism = Column(String(32), nullable=False)                  # api | replica | export | webhook
    is_authoritative = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class SyncCursor(Base):
    """Resumable position per (source_system, entity). Makes ingest restartable."""
    __tablename__ = "sync_cursors"
    id = Column(Integer, primary_key=True)
    source_system_id = Column(Integer, nullable=False)
    entity = Column(String(64), nullable=False)
    last_seen_version = Column(String(128), nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("source_system_id", "entity", name="uq_sync_cursor_system_entity"),
        Index("ix_sync_cursor_system_entity", "source_system_id", "entity"),
    )


class MirrorEvent(Base):
    """Append-only record of what arrived and what happened to it. The audit trail."""
    __tablename__ = "mirror_events"
    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),  # sqlite only autoincrements INTEGER pk
        primary_key=True,
    )
    source_system_id = Column(Integer, nullable=False)
    entity = Column(String(64), nullable=False)
    source_id = Column(String(128), nullable=False)
    source_version = Column(String(128), nullable=True)
    payload_sha256 = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)      # inserted | superseded | skipped | rejected
    reason = Column(String(256), nullable=True)
    received_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    raw = Column(JSON, nullable=True)                # the payload as received, verbatim
    __table_args__ = (
        Index("ix_mirror_events_system_entity_received", "source_system_id", "entity", "received_at"),
        Index("ix_mirror_events_source_id", "source_id"),
    )


class ReconcileRun(Base):
    """One reconciliation attempt. Fail-closed: a run ends clean or it ends red."""
    __tablename__ = "reconcile_runs"
    id = Column(Integer, primary_key=True)
    source_system_id = Column(Integer, nullable=False)
    entity = Column(String(64), nullable=False)
    source_count = Column(Integer, nullable=False)
    mirror_count = Column(Integer, nullable=False)
    source_checksum = Column(String(64), nullable=False)
    mirror_checksum = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)      # clean | mismatch | errored
    detail = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class ProjectionLink(Base):
    """One row per mirrored record, recording what it became in the domain.

    The mirror is append-only staging; the domain tables are what the product
    reads. This is the join between them, and the reason re-projection is safe:
    a second projection of the same (source_system, entity, source_id) updates
    `domain_id`'s row rather than inserting a duplicate.

    `status` is 'projected' or 'unmapped'. An unmapped row is not a failure to
    hide — MacSoft's field names have not been seen yet, so some records will
    not resolve on the first pass. Recording why (in `reason`) is what makes
    the next mapping pass targeted instead of guesswork, and it is surfaced by
    GET /webhooks/macsoft/status so nobody has to read logs to find it.
    """
    __tablename__ = "projection_links"
    id = Column(Integer, primary_key=True)
    source_system_id = Column(Integer, nullable=False)
    entity = Column(String(64), nullable=False)
    source_id = Column(String(256), nullable=False)
    status = Column(String(16), nullable=False)          # projected | unmapped
    domain_table = Column(String(64), nullable=True)     # orders | menu_items | inventory_items
    domain_id = Column(Integer, nullable=True)
    projected_version = Column(String(128), nullable=True)
    reason = Column(String(256), nullable=True)
    projected_at = Column(DateTime, nullable=True, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("source_system_id", "entity", "source_id",
                         name="uq_projection_link_identity"),
        Index("ix_projection_links_status", "source_system_id", "status"),
    )
