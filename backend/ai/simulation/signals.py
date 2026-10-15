"""
backend/ai/simulation/signals.py
──────────────────────────────────
External demand signals for the Digital Twin — the exogenous factors a plain
sales-history forecast can't see: public holidays, school-term breaks, (later)
weather and match days.

Design: a small pluggable PROVIDER interface. Each provider maps a date to zero
or more `Signal`s (a demand multiplier + a plain reason + a confidence). Ship
now, fully OFFLINE (no API keys): Kenyan public holidays and school-term breaks
as reference data. Deferred behind the SAME interface: live weather and sports
fixtures — their providers are present but return nothing until a key is
configured (mirrors payments/mpesa_client.py's "degrade to not_configured").

Honesty (directives/012): these multipliers are documented, conservative
assumptions about how each factor moves restaurant demand — not measured for
this specific restaurant. They are clearly separated from the sales-history
baseline (which the twin gets from revenue_forecaster) so the exogenous
adjustment is always visible and auditable, never silently baked in.

IMPORTANT: providers here must only add factors NOT already in the forecaster's
baseline. Day-of-week and general trend are already in the baseline, so there is
deliberately no "weekend" provider — that would double-count.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Callable

logger = logging.getLogger(__name__)


class Signal(NamedTuple):
    factor: float       # multiplicative demand effect (1.0 = no effect)
    reason: str         # plain-language cause
    confidence: int     # 0..100 — how sure we are this factor applies/matters


# Sane clamp so no combination of factors produces an absurd projection.
_FACTOR_MIN, _FACTOR_MAX = 0.7, 1.5


# ─────────────────────────────────────────────────────────────────────────────
# Reference data (offline), one file per year: backend/data/ke_holidays_<year>.json
#
# D12: the holidays were hard-coded for 2026 only, so from 1 Jan 2027 the twin and the reorder demand factor
# silently lost every holiday signal. Each year is now a data file (2026 and 2027 ship; adding a year is adding
# a file, no code change). A year with no file is NEUTRAL — no holiday signal, never an error — and is logged once.
# Eid dates are moon-dependent and flagged "approximate" in the file; they carry lower confidence.
# ─────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=None)
def _year_data(year: int) -> dict:
    """{"holidays": {date: (name, approximate)}, "school_breaks": [(start, end, label)]} for one year."""
    path = _DATA_DIR / f"ke_holidays_{year}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {
            "holidays": {date.fromisoformat(h["date"]): (h["name"], bool(h.get("approximate")))
                         for h in doc.get("public_holidays", [])},
            "school_breaks": [(date.fromisoformat(w["start"]), date.fromisoformat(w["end"]), w.get("label", ""))
                              for w in doc.get("school_breaks", [])],
        }
    except FileNotFoundError:
        logger.warning("no holiday file for %s (%s): no holiday or school-break signal for that year", year, path.name)
    except (ValueError, KeyError, TypeError):
        logger.exception("holiday file %s is malformed: no holiday or school-break signal for %s", path.name, year)
    return {"holidays": {}, "school_breaks": []}


# A public holiday tends to lift restaurant/leisure demand.
HOLIDAY_FACTOR = 1.15

SCHOOL_BREAK_FACTOR = 1.08


# ─────────────────────────────────────────────────────────────────────────────
# Providers  (Callable[[date], list[Signal]])
# ─────────────────────────────────────────────────────────────────────────────

def holiday_provider(d: date) -> list[Signal]:
    entry = _year_data(d.year)["holidays"].get(d)
    if not entry:
        return []
    name, approximate = entry
    confidence = 55 if approximate else 75
    label = f"{name} (approx.)" if approximate else name
    return [Signal(HOLIDAY_FACTOR, f"Public holiday: {label}", confidence)]


def school_break_provider(d: date) -> list[Signal]:
    for start, end, _label in _year_data(d.year)["school_breaks"]:
        if start <= d <= end:
            return [Signal(SCHOOL_BREAK_FACTOR, "School holidays — more family dining", 55)]
    return []


def weather_provider(d: date) -> list[Signal]:
    """Deferred: live weather. No-op until WEATHER_API_KEY is configured, so the
    twin runs today on offline signals and gains weather for free later."""
    if not os.getenv("WEATHER_API_KEY"):
        return []
    return []   # real integration slots in here behind the same interface


def sports_provider(d: date) -> list[Signal]:
    """Deferred: local match-day fixtures. No-op until SPORTS_API_KEY is set."""
    if not os.getenv("SPORTS_API_KEY"):
        return []
    return []


# The active provider set. New providers plug in here; nothing else changes.
_PROVIDERS: list[Callable[[date], list[Signal]]] = [
    holiday_provider,
    school_break_provider,
    weather_provider,
    sports_provider,
]


def demand_signals(d: date) -> dict:
    """
    Combined exogenous demand adjustment for one date. Factors combine
    multiplicatively (clamped); confidence is the LOWEST contributing confidence
    (a chain is only as sure as its least-certain link). No signals → neutral.
    """
    signals: list[Signal] = []
    for provider in _PROVIDERS:
        try:
            signals.extend(provider(d))
        except Exception:  # noqa: BLE001 — a bad provider must not break the twin
            continue

    if not signals:
        return {"factor": 1.0, "confidence": 100, "reasons": [], "date": d.isoformat()}

    factor = 1.0
    for s in signals:
        factor *= s.factor
    factor = max(_FACTOR_MIN, min(_FACTOR_MAX, factor))

    return {
        "factor": round(factor, 3),
        "confidence": min(s.confidence for s in signals),
        "reasons": [s.reason for s in signals],
        "date": d.isoformat(),
    }
