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

import models
from database import SessionLocal
from leviii_test_seed import ensure_eleven_test_data
from models import Base


def seed(credentials_path: Path, owner_password: str | None = None) -> None:
    from database import engine

    if str(engine.url).startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    password = owner_password or secrets.token_urlsafe(12)
    owner_password_line = f"OWNER_PASSWORD={password}"
    db = SessionLocal()
    try:
        existed = db.query(models.User).filter(models.User.email == "owner@eleven.leviii").first() is not None
        ensure_eleven_test_data(db, password)
        if existed and owner_password is None:
            owner_password_line = "OWNER_PASSWORD=(unchanged — existing account)"
        credentials_path.parent.mkdir(parents=True, exist_ok=True)
        credentials_path.write_text(
            "\n".join(
                [
                    "# Jack test site owner login (do not commit)",
                    "RESTAURANT=Eleven",
                    "OWNER_EMAIL=owner@eleven.leviii",
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
    parser.add_argument(
        "--owner-password",
        default="",
        help="Use a fixed owner password instead of generating one (not logged).",
    )
    args = parser.parse_args()
    fixed = args.owner_password.strip() or None
    seed(Path(args.credentials), owner_password=fixed)
    if not args.quiet:
        sys.stdout.write(f"credentials written: {args.credentials}\n")