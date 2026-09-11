"""The source client must be incapable of writing to the client system."""
from __future__ import annotations

import pytest

from integration.source_client import ReadOnlySourceClient, SourceSystemError


def client() -> ReadOnlySourceClient:
    return ReadOnlySourceClient("https://source.example.invalid", "token")


def test_non_http_base_url_is_refused() -> None:
    with pytest.raises(SourceSystemError):
        ReadOnlySourceClient("ftp://source.example.invalid", "token")


def test_post_is_refused_before_any_network_call() -> None:
    with pytest.raises(SourceSystemError, match="read-only"):
        client()._request("POST", "/orders", id=1)


def test_delete_is_refused_before_any_network_call() -> None:
    with pytest.raises(SourceSystemError, match="read-only"):
        client()._request("DELETE", "/orders/1")


def test_no_write_method_exists_on_the_class() -> None:
    public = {n for n in dir(ReadOnlySourceClient) if not n.startswith("_")}
    for forbidden in ("post", "put", "patch", "delete", "create", "update"):
        assert forbidden not in public, f"{forbidden} must not be part of the read-only client"
