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

import os
from datetime import date
from typing import NamedTuple, Callable


class Signal(NamedTuple):
    factor: float       # multiplicative demand effect (1.0 = no effect)
    reason: str         # plain-language cause
    confidence: int     # 0..100 — how sure we are this factor applies/matters


# Sane clamp so no combination of factors produces an absurd projection.
_FACTOR_MIN, _FACTOR_MAX = 0.7, 1.5


# ─────────────────────────────────────────────────────────────────────────────
# Reference data (offline). 2026, Kenya. Approximate for moon-dependent Eid
# dates — flagged with lower confidence accordingly.
# ─────────────────────────────────────────────────────────────────────────────

KENYA_PUBLIC_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 3, 20): "Eid al-Fitr (approx.)",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 6): "Easter Monday",
    date(2026, 5, 1): "Labour Day",
    date(2026, 5, 27): "Eid al-Adha (approx.)",
    date(2026, 6, 1): "Madaraka Day",
    date(2026, 10, 10): "Huduma Day",
    date(2026, 10, 20): "Mashujaa Day",
    date(2026, 12, 12): "Jamhuri Day",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 26): "Utamaduni Day",
}

# Approximate Eid dates carry lower confidence (moon-dependent).
_APPROX_HOLIDAYS = {date(2026, 3, 20), date(2026, 5, 27)}

# A public holiday tends to lift restaurant/leisure demand.
HOLIDAY_FACTOR = 1.15

# School-break windows (families dine out more). Approximate 2026 Kenyan terms.
SCHOOL_BREAK_WINDOWS_2026: list[tuple[date, date]] = [
    (date(2026, 1, 1), date(2026, 1, 5)),      # pre-Term-1
    (date(2026, 4, 11), date(2026, 4, 26)),    # Term-1 break
    (date(2026, 8, 8), date(2026, 8, 30)),     # Term-2 break
    (date(2026, 10, 24), date(2026, 12, 31)),  # post-Term-3 / December holidays
]
SCHOOL_BREAK_FACTOR = 1.08


# ─────────────────────────────────────────────────────────────────────────────
# Providers  (Callable[[date], list[Signal]])
# ─────────────────────────────────────────────────────────────────────────────

def holiday_provider(d: date) -> list[Signal]:
    name = KENYA_PUBLIC_HOLIDAYS_2026.get(d)
    if not name:
        return []
    confidence = 55 if d in _APPROX_HOLIDAYS else 75
    return [Signal(HOLIDAY_FACTOR, f"Public holiday: {name}", confidence)]


def school_break_provider(d: date) -> list[Signal]:
    for start, end in SCHOOL_BREAK_WINDOWS_2026:
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
