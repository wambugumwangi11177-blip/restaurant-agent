"""
Pluggable object storage (Phase 9): local-backend round trip. The S3 branch is
config-gated and not exercised here (no bucket in CI).
"""

import importlib


def test_local_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
    import storage
    importlib.reload(storage)  # pick up the env under test

    key = storage.save(b"hello bytes", content_type="text/plain")
    assert storage.exists(key) is True
    assert storage.load(key) == b"hello bytes"
    assert storage.url(key) == f"/files/{key}"

    storage.delete(key)
    assert storage.exists(key) is False


def test_explicit_key_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
    import storage
    importlib.reload(storage)

    key = storage.save(b"x", key="menu/photo1.jpg")
    assert key == "menu/photo1.jpg"
    assert storage.exists("menu/photo1.jpg")
