"""
Departments, built one at a time on the Kernel (directive 000). Each module
exposes `register()`; its SQLAlchemy models are imported with the module so
Alembic sees them. Departments never import each other (ADR 0001).
"""

from __future__ import annotations

import importlib

# Order = build order in directive 000.
MODULES = ["command", "sales", "delivery", "support", "finance", "legal", "marketing", "product", "people"]


def _active() -> list[str]:
    # COS_DEPARTMENTS limits loading (used only to generate one migration per department).
    import os

    limit = os.environ.get("COS_DEPARTMENTS")
    return MODULES if limit is None else [m for m in MODULES if m in limit.split(",")]


def import_models() -> None:
    for name in _active():
        importlib.import_module(f"app.departments.{name}")


def register_all() -> None:
    for name in _active():
        importlib.import_module(f"app.departments.{name}").register()
