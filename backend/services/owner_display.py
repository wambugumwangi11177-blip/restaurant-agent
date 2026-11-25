"""Strip demo markers and polish labels for owner-facing copy."""
from __future__ import annotations

import re

_DEMO = re.compile(r"\[DEMO\]\s*", re.IGNORECASE)


def owner_facing_label(text: str | None) -> str:
    if not text:
        return ""
    cleaned = _DEMO.sub("", text).strip()
    low = cleaned.lower()
    if "kplc" in low and ("unknown" in low or cleaned.endswith("— amount unknown")):
        return "KPLC electricity bill, amount needed"
    return cleaned


def owner_facing_text(text: str | None) -> str:
    if not text:
        return ""
    return _DEMO.sub("", text).strip()