"""Scheduled owner reports → in-app notification + reports list."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

import models
from ai.notify import notify_user
from routers.deps import get_staff_users_for_restaurant
from services.owner_prefs import read_prefs
from time_utils import utcnow

logger = logging.getLogger("owner_reports")


def _append_report(restaurant: models.Restaurant, entry: dict) -> None:
    prefs = read_prefs(restaurant)
    raw = {}
    try:
        raw = json.loads(restaurant.staple_caps_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    block = raw.get("__owner_v11__") if isinstance(raw.get("__owner_v11__"), dict) else {}
    reports = block.get("reports_past") if isinstance(block.get("reports_past"), list) else []
    reports.insert(0, entry)
    block["reports_past"] = reports[:50]
    raw["__owner_v11__"] = block
    restaurant.staple_caps_json = json.dumps(raw)


def _owners(db: Session, restaurant: models.Restaurant):
    return get_staff_users_for_restaurant(db, restaurant, [models.StaffRole.OWNER])


def run_daily_report(db: Session, restaurant_id: int) -> None:
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if not restaurant:
        return
    day = utcnow().date().isoformat()
    entry = {
        "id": f"daily-{day}",
        "kind": "daily",
        "title": f"Daily store report — {day}",
        "created_at": utcnow().isoformat(),
        "href": "/eleven/reports",
    }
    _append_report(restaurant, entry)
    for u in _owners(db, restaurant):
        notify_user(db, u.id, "Daily report ready", f"Store report for {day} is in Reports.", "owner.report.daily", url="/eleven/settings/reports")
    db.commit()


def run_weekly_report(db: Session, restaurant_id: int) -> None:
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if not restaurant:
        return
    week = utcnow().strftime("%Y-W%W")
    entry = {"id": f"weekly-{week}", "kind": "weekly", "title": f"Weekly summary — {week}", "created_at": utcnow().isoformat(), "href": "/eleven/settings/reports"}
    _append_report(restaurant, entry)
    for u in _owners(db, restaurant):
        notify_user(db, u.id, "Weekly report ready", "Your Monday weekly summary is in Reports.", "owner.report.weekly", url="/eleven/settings/reports")
    db.commit()


def run_monthly_pnl_report(db: Session, restaurant_id: int) -> None:
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if not restaurant:
        return
    period = utcnow().strftime("%Y-%m")
    entry = {
        "id": f"monthly-{period}",
        "kind": "monthly",
        "title": f"Monthly P&L — {period}",
        "created_at": utcnow().isoformat(),
        "href": f"/api/v1/eleven/money/export/monthly/{period}.xlsx",
    }
    _append_report(restaurant, entry)
    for u in _owners(db, restaurant):
        notify_user(db, u.id, "Monthly P&L ready", f"Final P&L for {period} is ready to download.", "owner.report.monthly", url="/eleven/money/pnl")
    db.commit()


def run_all_restaurants(job_kind: str) -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        for rid in [r.id for r in db.query(models.Restaurant.id).all()]:
            try:
                if job_kind == "daily":
                    run_daily_report(db, rid)
                elif job_kind == "weekly":
                    run_weekly_report(db, rid)
                elif job_kind == "monthly":
                    run_monthly_pnl_report(db, rid)
            except Exception as exc:
                logger.warning("owner report %s restaurant %s: %s", job_kind, rid, exc)
                db.rollback()
    finally:
        db.close()