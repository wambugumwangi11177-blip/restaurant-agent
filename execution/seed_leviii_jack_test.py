#!/usr/bin/env python3
"""Seed Eleven demo data for the Jack test stack. Writes owner creds to an artifacts file."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

os.environ.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", "leviii-test-seed-key"))

import auth
import models
from database import SessionLocal
from models import Base, Role, StaffRole, StaffSetupProgress


def seed(credentials_path: Path) -> None:
    # Railway jack-test runs alembic before this script. Local sqlite bootstrap only.
    from database import engine

    if str(engine.url).startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        owner_password = secrets.token_urlsafe(12)
        owner_password_line = f"OWNER_PASSWORD={owner_password}"
        tenant = db.query(models.Tenant).filter(models.Tenant.name == "Eleven").first()
        if tenant is None:
            tenant = models.Tenant(name="Eleven")
            db.add(tenant)
            db.flush()
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).first()
        if restaurant is None:
            restaurant = models.Restaurant(tenant_id=tenant.id, name="Eleven", address="Ngong Road")
            db.add(restaurant)
            db.flush()
        owner = db.query(models.User).filter(models.User.email == "owner@eleven.leviii").first()
        if owner is None:
            owner = models.User(
                email="owner@eleven.leviii",
                hashed_password=auth.get_password_hash(owner_password),
                role=Role.ADMIN,
                staff_role=StaffRole.OWNER,
                tenant_id=tenant.id,
                must_change_password=False,
                is_email_verified=True,
            )
            db.add(owner)
        else:
            owner_password_line = "OWNER_PASSWORD=(unchanged — existing account)"
        for email, role, name in (
            ("jack@eleven.leviii", StaffRole.STOCKKEEPER, "Jack"),
            ("amina@eleven.leviii", StaffRole.CONTROLLER, "Amina"),
        ):
            user = db.query(models.User).filter(models.User.email == email).first()
            if user is None:
                user = models.User(
                    email=email,
                    hashed_password=None,
                    role=Role.STAFF,
                    staff_role=role,
                    tenant_id=tenant.id,
                    must_change_password=True,
                )
                db.add(user)
                db.flush()
                db.add(
                    StaffSetupProgress(
                        user_id=user.id,
                        restaurant_id=restaurant.id,
                    )
                )
            if db.query(models.StaffMember).filter(
                models.StaffMember.restaurant_id == restaurant.id,
                models.StaffMember.user_id == user.id,
            ).first() is None:
                db.add(models.StaffMember(restaurant_id=restaurant.id, user_id=user.id, name=name, role_title=role.value))
        db.commit()
        credentials_path.parent.mkdir(parents=True, exist_ok=True)
        credentials_path.write_text(
            "\n".join(
                [
                    "# Jack test site owner login (do not commit)",
                    "RESTAURANT=Eleven",
                    f"OWNER_EMAIL=owner@eleven.leviii",
                    owner_password_line,
                    "JACK_EMAIL=jack@eleven.leviii",
                    "JACK_PASSWORD=set on first sign-in",
                    "ACCOUNTANT_EMAIL=amina@eleven.leviii",
                    "ACCOUNTANT_PASSWORD=set on first sign-in",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(credentials_path, 0o600)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--credentials",
        default="/opt/cursor/artifacts/leviii-jack-test-credentials.env",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the credentials path (file is still written).",
    )
    args = parser.parse_args()
    seed(Path(args.credentials))
    if not args.quiet:
        sys.stdout.write(f"credentials written: {args.credentials}\n")