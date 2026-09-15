"""Vendor-neutral, read-only source contract for the observer deployment."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True)
class SourceHealth:
    source: str
    state: str  # connected | unavailable | stale | incomplete
    checked_at: datetime | None = None
    as_of: datetime | None = None
    capabilities: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class Sale:
    external_id: str
    restaurant_external_id: str
    occurred_at: datetime
    amount_minor: int
    status: str


@dataclass(frozen=True)
class Tender:
    external_id: str
    sale_external_id: str | None
    occurred_at: datetime
    amount_minor: int
    method: str
    status: str
    reversal_of_external_id: str | None = None


class RestaurantSource(Protocol):
    """A bounded read-only adapter. Vendor field mapping belongs in its implementation."""
    async def health(self, restaurant_id: int) -> SourceHealth: ...
    async def sales(self, restaurant_id: int, start: datetime, end: datetime) -> Sequence[Sale]: ...
    async def tenders(self, restaurant_id: int, start: datetime, end: datetime) -> Sequence[Tender]: ...


class UnconfiguredSource:
    async def health(self, restaurant_id: int) -> SourceHealth:
        return SourceHealth(
            source="Macsoft", state="unavailable",
            reason="Macsoft has not been connected for this restaurant yet.",
        )

    async def sales(self, restaurant_id: int, start: datetime, end: datetime) -> Sequence[Sale]:
        return ()

    async def tenders(self, restaurant_id: int, start: datetime, end: datetime) -> Sequence[Tender]:
        return ()


class SourceRegistry:
    """Adapter registration requires an explicit, already-approved restaurant ID."""
    def __init__(self) -> None:
        self._fallback: RestaurantSource = UnconfiguredSource()
        self._sources: dict[int, RestaurantSource] = {}

    def register(self, restaurant_id: int, source: RestaurantSource) -> None:
        if restaurant_id <= 0:
            raise ValueError("restaurant_id must be positive")
        self._sources[restaurant_id] = source

    def resolve(self, restaurant_id: int | None) -> RestaurantSource:
        return self._sources.get(restaurant_id or 0, self._fallback)
