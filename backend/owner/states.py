"""
backend/owner/states.py — what state is this number in? (docs/v2/SPEC.md §0.3)

"Every number carries its state. The owner never sees an estimate dressed as a fact." One function family,
used by every block of every owner payload:

  live          derived from till/order data that is no more than 3 days old
  as_entered    derived from rows a person typed or counted (stock counts, drawer counts, bills): carries
                `entered_up_to` — the Nairobi date of the latest entry
  learning      not enough history yet: carries `day` and `of` ("day 9 of 30")
  not_from_pos  computed from something other than the till (a bank / M-Pesa statement): carries `source`
  stale         the latest data is older than 3 days: carries `as_of`
  assumption    (an optional field on any block, not a state of its own) the rule used:
                `assumption: {setting, value}` so the owner can see — and change — what the number is based on
  no_data       nothing recorded yet (a fresh tenant): honest, not an error
  unavailable   not built yet, or the engine could not run: carries a plain `reason`

`OwnerContext` is one request's worth of shared facts (restaurant, settings, freshness, memoised engine
output) so that twenty blocks do not each re-ask the database the same questions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from ai.analysis_clock import STALE_AFTER_DAYS
from owner.settings import Settings, get_settings
from time_utils import eat_date, utcnow

logger = logging.getLogger("owner")

LEARNING_DAYS = 30        # "day n of 30"
STATES = ("live", "as_entered", "learning", "not_from_pos", "stale", "no_data", "unavailable")


def iso(dt: datetime | None) -> str | None:
    """A naive-UTC database timestamp as an unambiguous ISO-8601 string (explicit +00:00)."""
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt is not None else None


def block(state: str, *, as_of: datetime | str | None = None, assumption: dict | None = None,
          assumptions: list[dict] | None = None, **fields: Any) -> dict:
    """The common shape of every owner block: {state, as_of, [assumption(s)], ...fields}."""
    assert state in STATES, state
    out: dict[str, Any] = {"state": state, "as_of": iso(as_of) if isinstance(as_of, datetime) else as_of}
    if assumptions:
        out["assumptions"] = assumptions
        out["assumption"] = assumptions[0]
    elif assumption:
        out["assumption"] = assumption
    out.update(fields)
    return out


def unavailable(reason: str, **fields: Any) -> dict:
    return block("unavailable", reason=reason, **fields)


def no_data(reason: str = "Nothing recorded yet.", **fields: Any) -> dict:
    return block("no_data", reason=reason, **fields)


def assume(setting: str, value: Any, *, label: str | None = None) -> dict:
    """`assumption: {setting, value}` — the rule behind a number, by the setting that owns it."""
    out = {"setting": setting, "value": value}
    if label:
        out["label"] = label
    return out


class OwnerContext:
    """Everything one owner request shares: who, which restaurant, settings, how fresh the data is."""

    def __init__(self, db: Session, user: models.User, restaurant: models.Restaurant,
                 settings: Settings | None = None):
        self.db = db
        self.user = user
        self.restaurant = restaurant
        self.rid = restaurant.id
        self.tenant_id = restaurant.tenant_id
        self.settings = settings if settings is not None else get_settings(db, restaurant.id)
        self.now = utcnow()
        self._cache: dict[str, Any] = {}
        self._orders: tuple | None = None

    # ── memoised engine output ───────────────────────────────────────────────
    def cached(self, key: str, fn: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # ── order data: how fresh, how much history ──────────────────────────────
    def _order_span(self) -> tuple[datetime | None, datetime | None]:
        if self._orders is None:
            first, latest = self.db.query(func.min(models.Order.created_at), func.max(models.Order.created_at)).filter(
                models.Order.restaurant_id == self.rid).one()
            self._orders = (first, latest)
        return self._orders

    @property
    def latest_order_at(self) -> datetime | None:
        return self._order_span()[1]

    @property
    def history_days(self) -> int:
        first, latest = self._order_span()
        return 0 if first is None or latest is None else (latest - first).days + 1

    def order_state(self, *, needs_days: int = 0, **fields: Any) -> dict:
        """The state of a number derived from order data.

        no_data if there are no orders; stale if the newest order is over 3 days old; learning if the
        restaurant has fewer than `needs_days` days of history; otherwise live.
        """
        first, latest = self._order_span()
        if latest is None:
            return no_data("No sales recorded yet.", **fields)
        age_days = max((self.now - latest).days, 0)
        if age_days > STALE_AFTER_DAYS:
            return block("stale", as_of=latest, age_days=age_days, **fields)
        if needs_days and self.history_days < needs_days:
            return block("learning", as_of=latest, day=self.history_days, of=needs_days, **fields)
        return block("live", as_of=latest, **fields)

    def entered_state(self, latest_entry: datetime | None, *, empty: str = "Nothing entered yet.", **fields: Any) -> dict:
        """The state of a number derived from rows a person typed or counted."""
        if latest_entry is None:
            return no_data(empty, **fields)
        return block("as_entered", as_of=latest_entry, entered_up_to=eat_date(latest_entry).isoformat(), **fields)

    # ── failure isolation: one engine failing never takes Home down ──────────
    def safe(self, name: str, fn: Callable[[], dict]) -> dict:
        try:
            with self.db.begin_nested():
                return fn()
        except Exception:  # noqa: BLE001 — Home must always render
            logger.exception("owner block %s failed for restaurant %s", name, self.rid)
            return unavailable("This part could not be read just now.")


def kes(cents: float | int | None) -> float | None:
    """Integer cents (inside the backend) → KES at the edge, to the cent."""
    return None if cents is None else round(cents / 100.0, 2)
