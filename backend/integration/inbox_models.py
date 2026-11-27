"""Durable QuickSell receipts. Shares application metadata for scoped foreign keys."""
from sqlalchemy import (Column, DateTime, ForeignKey, ForeignKeyConstraint, Index,
                        Integer, JSON, String, Text, UniqueConstraint)
from models import Base
from time_utils import utcnow


class PosSourceBinding(Base):
    __tablename__ = "pos_source_bindings"
    id = Column(Integer, primary_key=True)
    slug = Column(String(64), nullable=False, unique=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("id", "restaurant_id", name="uq_pos_binding_scope"),)


class PosInbox(Base):
    __tablename__ = "pos_inbox"
    id = Column(String(36), primary_key=True)
    binding_id = Column(Integer, nullable=False)
    restaurant_id = Column(Integer, nullable=False)
    # Original UTF-8 envelope, including wrapper fields. Never copied to logs/AI.
    raw_body = Column(Text, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    received_at = Column(DateTime, nullable=False, default=utcnow)
    status = Column(String(24), nullable=False, default="pending")
    parser_version = Column(String(48), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    parsed_at = Column(DateTime, nullable=True)
    error_code = Column(String(48), nullable=True)
    result = Column(JSON, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(["binding_id", "restaurant_id"], ["pos_source_bindings.id", "pos_source_bindings.restaurant_id"], ondelete="RESTRICT"),
        UniqueConstraint("id", "binding_id", name="uq_pos_inbox_source"),
        Index("ix_pos_inbox_scope_status_time", "restaurant_id", "status", "received_at"),
    )


class PosAppliedRecord(Base):
    __tablename__ = "pos_applied_records"
    id = Column(Integer, primary_key=True)
    binding_id = Column(Integer, nullable=False)
    inbox_id = Column(String(36), nullable=False)
    entity = Column(String(64), nullable=False)
    source_id = Column(String(128), nullable=False)
    source_version = Column(String(128), nullable=False)
    applied_at = Column(DateTime, nullable=False, default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(["inbox_id", "binding_id"], ["pos_inbox.id", "pos_inbox.binding_id"], ondelete="RESTRICT"),
        UniqueConstraint("binding_id", "entity", "source_id", "source_version", name="uq_pos_applied_identity"),
    )


class PosParseAttempt(Base):
    __tablename__ = "pos_parse_attempts"
    id = Column(Integer, primary_key=True)
    inbox_id = Column(String(36), ForeignKey("pos_inbox.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    parser_version = Column(String(48), nullable=False)
    outcome = Column(String(24), nullable=False)
    error_code = Column(String(48), nullable=True)
    attempted_at = Column(DateTime, nullable=False, default=utcnow)
