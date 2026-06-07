"""
backend/security_audit.py
───────────────────────────
Security audit logging for authentication and authorization events.
"""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

import models
from database import SessionLocal

logger = logging.getLogger("security.audit")


def log_auth_event(
    db: Session,
    event_type: str,
    user_email: Optional[str] = None,
    tenant_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    success: bool = True,
    failure_reason: Optional[str] = None,
    details: Optional[dict] = None,
):
    """
    Log a security-related authentication event.
    """
    try:
        audit_log = models.SecurityAuditLog(
            event_type=event_type,
            user_email=user_email,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason,
            details=details or {},
            timestamp=datetime.utcnow(),
        )
        db.add(audit_log)
        db.commit()
        logger.info(f"Security audit logged: {event_type} for {user_email} - success={success}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to write security audit log: {e}")


def log_auth_failure(
    db: Session,
    event_type: str,
    user_email: Optional[str] = None,
    tenant_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    failure_reason: str = "",
    details: Optional[dict] = None,
):
    """Convenience function for logging failed auth events."""
    log_auth_event(
        db=db,
        event_type=event_type,
        user_email=user_email,
        tenant_id=tenant_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False,
        failure_reason=failure_reason,
        details=details,
    )


def log_auth_success(
    db: Session,
    event_type: str,
    user_email: Optional[str] = None,
    tenant_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
):
    """Convenience function for logging successful auth events."""
    log_auth_event(
        db=db,
        event_type=event_type,
        user_email=user_email,
        tenant_id=tenant_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        failure_reason=None,
        details=details,
    )