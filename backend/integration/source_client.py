"""Read-only HTTP client for a client source system.

Hard rule: this client can only GET. There is no post/put/patch/delete method
and `_request` asserts the verb. If a future integration needs to write back to
the client system, that requires a separate, explicitly-authorized module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterator

import requests

_ALLOWED_VERBS = frozenset({"GET"})


class SourceSystemError(RuntimeError):
    pass


@dataclass(frozen=True)
class Page:
    items: list[dict[str, Any]]
    next_cursor: str | None
    checksum: str


class ReadOnlySourceClient:
    def __init__(self, base_url: str, token: str, *, timeout_s: int = 30, page_size: int = 200) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise SourceSystemError(f"base_url must be http(s), got {base_url!r}")
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        self._timeout = timeout_s
        self._page_size = page_size

    def _request(self, method: str, path: str, **params: Any) -> dict[str, Any]:
        if method not in _ALLOWED_VERBS:
            raise SourceSystemError(f"refusing non-read verb {method!r}: this client is read-only")
        resp = self._session.request(method, f"{self._base}{path}", params=params, timeout=self._timeout)
        if resp.status_code == 429:
            raise SourceSystemError("source system rate-limited (429); back off and resume from cursor")
        resp.raise_for_status()
        return resp.json()

    def iter_entity(self, entity: str, *, since_version: str | None = None) -> Iterator[Page]:
        cursor: str | None = None
        while True:
            body = self._request(
                "GET", f"/{entity}", limit=self._page_size, cursor=cursor, since=since_version
            )
            items = body.get("items", [])
            digest = hashlib.sha256(
                json.dumps(items, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            yield Page(items=items, next_cursor=body.get("next_cursor"), checksum=digest)
            cursor = body.get("next_cursor")
            if not cursor:
                return
