"""
app/departments/ical.py
───────────────────────
Minimal iCalendar (RFC 5545) reader for "what's on my calendar today".

Why iCal and not the Google Calendar API: Google Calendar exposes a private
"Secret address in iCal format" per calendar, which needs no OAuth app,
review or token refresh. The founder pastes it into workspace settings
(`calendar_ical_url`, stored masked).

Supported subset (deliberately small, and tested):
  - line unfolding, VEVENT blocks, SUMMARY / LOCATION with text unescaping
  - DTSTART / DTEND as UTC (…Z), with TZID=<IANA zone>, floating local, or VALUE=DATE (all-day)
  - STATUS:CANCELLED events are skipped
NOT supported: RRULE expansion. Recurring events whose first occurrence is not
today are *counted and reported* as "not shown", never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx


@dataclass(frozen=True)
class CalEvent:
    summary: str
    start: datetime | date
    all_day: bool
    location: str = ""
    recurring: bool = False


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _parse_dt(params: dict[str, str], value: str, default_tz: ZoneInfo) -> tuple[datetime | date, bool]:
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])), True
    base = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return base.replace(tzinfo=timezone.utc), False
    tz = default_tz
    if "TZID" in params:
        try:
            tz = ZoneInfo(params["TZID"].strip('"'))
        except ZoneInfoNotFoundError:
            tz = default_tz  # Windows-style TZIDs etc.: fall back to the workspace zone
    return base.replace(tzinfo=tz), False


def parse_events(text: str, default_tz: str = "Africa/Nairobi") -> list[CalEvent]:
    tz = ZoneInfo(default_tz)
    events: list[CalEvent] = []
    cur: dict | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
            continue
        if line == "END:VEVENT":
            if cur and "start" in cur and cur.get("status") != "CANCELLED":
                events.append(CalEvent(cur.get("summary", "(no title)"), cur["start"], cur["all_day"],
                                       cur.get("location", ""), cur.get("recurring", False)))
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *raw_params = head.split(";")
        params = dict(p.split("=", 1) for p in raw_params if "=" in p)
        name = name.upper()
        if name == "SUMMARY":
            cur["summary"] = _unescape(value)
        elif name == "LOCATION":
            cur["location"] = _unescape(value)
        elif name == "STATUS":
            cur["status"] = value.strip().upper()
        elif name == "RRULE":
            cur["recurring"] = True
        elif name == "DTSTART":
            try:
                cur["start"], cur["all_day"] = _parse_dt(params, value.strip(), tz)
            except ValueError:
                pass  # malformed date: skip the field rather than guess
    return events


def events_on(events: list[CalEvent], day: date, tz: str) -> tuple[list[CalEvent], int]:
    """(events on `day` in zone `tz`, count of recurring events not expanded)."""
    zone = ZoneInfo(tz)
    today: list[CalEvent] = []
    skipped_recurring = 0
    for e in events:
        d = e.start if e.all_day else e.start.astimezone(zone).date()
        if d == day:
            today.append(e)
        elif e.recurring and d < day:
            skipped_recurring += 1
    today.sort(key=lambda e: (not e.all_day, e.start if not e.all_day else datetime.min.replace(tzinfo=timezone.utc)))
    return today, skipped_recurring


def fetch(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError("calendar URL must be https")
    r = httpx.get(url, timeout=15, follow_redirects=True)
    r.raise_for_status()
    return r.text[:5_000_000]
