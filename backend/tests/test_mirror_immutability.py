"""Mirrored rows must never be updated in place (integration design rule 2)."""
from __future__ import annotations

import hashlib
import json

import pytest


def test_source_version_is_part_of_the_identity() -> None:
    from integration.models import MirrorEvent

    cols = {c.name for c in MirrorEvent.__table__.columns}
    assert {"source_system_id", "entity", "source_id", "source_version"} <= cols


def test_payload_hash_is_stored_for_every_event() -> None:
    from integration.models import MirrorEvent

    cols = {c.name for c in MirrorEvent.__table__.columns}
    assert "payload_sha256" in cols


def test_identical_payload_yields_identical_hash() -> None:
    a = hashlib.sha256(json.dumps({"id": 1, "total": 500}, sort_keys=True).encode()).hexdigest()
    b = hashlib.sha256(json.dumps({"total": 500, "id": 1}, sort_keys=True).encode()).hexdigest()
    assert a == b, "hash must be stable across key order or reconcile checksums are meaningless"


def test_mirror_event_has_no_mutable_state_column_that_overwrites_history() -> None:
    from integration.models import MirrorEvent

    assert "updated_at" not in {c.name for c in MirrorEvent.__table__.columns}, (
        "MirrorEvent is append-only; an updated_at column invites in-place edits"
    )
