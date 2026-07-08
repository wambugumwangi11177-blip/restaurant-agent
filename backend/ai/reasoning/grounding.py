"""
backend/ai/reasoning/grounding.py
───────────────────────────────────
Number-faithfulness guard for the reasoning layer.

The LLM is told to speak qualitatively and never invent figures — but a smaller
model still occasionally slips a wrong number into prose (observed: it wrote
"23% commission" when the data said 25%). This module is the enforcement: it
extracts every meaningful number from the LLM's text and checks each one is
actually present in (or trivially derivable from) the deterministic payload the
narrative was built from. Ungrounded numbers are redacted to a marker and
reported, so a hallucinated figure can never reach the owner as if it were real.

Design choices, and why:
  • Only "checkable" numbers are policed — anything with %, a currency marker, a
    decimal point, or magnitude ≥ 10. Bare small integers ("your 3 channels")
    are almost always counts/ordinals, are low-risk, and policing them causes
    false positives, so they're skipped.
  • Grounding is tolerant of representation. The payload stores money in cents
    and ratios as fractions; the model quite reasonably says "KES 9,000" for
    900000 cents or "25%" for 0.25. So the grounded set includes each raw number
    PLUS common derivations (÷100 for cents→currency, ×100 for ratio→percent)
    and rounded forms. Matching is within a small relative tolerance so
    "58%" grounds against 58.3 but "23%" does NOT ground against 25.
  • Enforcement redacts in place rather than dropping whole sentences — the
    qualitative judgement survives; only the false digit is removed.
"""

import re

# A number is worth policing if it carries a %/currency/decimal signal or is
# reasonably large. This keeps the guard focused on the figures that actually
# mislead (prices, percentages, volumes) and off harmless counts.
_MIN_CHECKABLE_MAGNITUDE = 10.0

# Relative tolerance for "does this output number match a grounded one".
# 1% absorbs rounding (58.3 → 58) without letting a genuinely different figure
# (23 vs 25, an 8% gap) sneak through.
_REL_TOL = 0.01

_REDACTION = "[unverified]"

# Matches: 1,234.56  |  1234  |  25%  |  KES 9,000  |  $12.50 — capturing the
# numeric core and any %/currency context so we can decide if it's "checkable".
_NUMBER_RE = re.compile(
    r"(?P<cur>KES\s*|\$\s*|USD\s*)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<pct>\s*%)?",
    re.IGNORECASE,
)


def collect_grounded_numbers(payload) -> set:
    """Every numeric value in the payload plus common derived representations."""
    raw: set = set()
    _walk(payload, raw)

    grounded: set = set()
    for n in raw:
        for v in _derivations(n):
            grounded.add(round(v, 4))
    return grounded


def _walk(obj, out: set) -> None:
    if isinstance(obj, bool):
        return  # bool is an int subclass — never treat True/False as a figure
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        return
    if isinstance(obj, dict):
        # list/dict lengths are legitimately citable ("your 3 delivery channels")
        out.add(float(len(obj)))
        for v in obj.values():
            _walk(v, out)
        return
    if isinstance(obj, (list, tuple)):
        out.add(float(len(obj)))
        for v in obj:
            _walk(v, out)
        return
    # numeric-looking strings ("58.3", "25%") count as grounded too
    if isinstance(obj, str):
        m = _NUMBER_RE.fullmatch(obj.strip())
        if m:
            try:
                out.add(float(m.group("num").replace(",", "")))
            except ValueError:
                pass


def _derivations(n: float) -> set:
    """The forms a model might reasonably write a payload number as."""
    forms = {n, round(n)}
    forms.add(n / 100.0)      # cents -> currency units
    forms.add(n * 100.0)      # ratio -> percent
    forms.add(round(n / 100.0))
    forms.add(round(n * 100.0))
    return {float(f) for f in forms}


def _is_grounded(value: float, grounded: set) -> bool:
    for g in grounded:
        if value == g:
            return True
        scale = max(abs(g), abs(value), 1.0)
        if abs(value - g) <= _REL_TOL * scale:
            return True
    return False


def _redact_text(text: str, grounded: set, ungrounded_out: list) -> str:
    if not text:
        return text

    def repl(m: re.Match) -> str:
        num_str = m.group("num")
        checkable = bool(m.group("pct") or m.group("cur")) or "." in num_str
        try:
            value = float(num_str.replace(",", ""))
        except ValueError:
            return m.group(0)
        if not checkable and value < _MIN_CHECKABLE_MAGNITUDE:
            return m.group(0)  # bare small integer — not policed
        if _is_grounded(value, grounded):
            return m.group(0)  # correct figure — leave it
        ungrounded_out.append(m.group(0).strip())
        return _REDACTION

    return _NUMBER_RE.sub(repl, text)


def verify(narrative: dict, payload) -> dict:
    """
    Return a copy of `narrative` with every ungrounded number in its text fields
    redacted, plus grounding metadata:
      verified           : True when no ungrounded numbers were found
      ungrounded_numbers : the offending figures (as written by the model)

    Never raises and never drops the qualitative content — only the false digits.
    """
    grounded = collect_grounded_numbers(payload)
    ungrounded: list = []

    clean = dict(narrative)
    if "headline" in clean:
        clean["headline"] = _redact_text(str(clean["headline"]), grounded, ungrounded)
    if isinstance(clean.get("priorities"), list):
        clean["priorities"] = [_redact_text(str(p), grounded, ungrounded) for p in clean["priorities"]]
    if isinstance(clean.get("actions"), list):
        new_actions = []
        for a in clean["actions"]:
            if isinstance(a, dict):
                a = {k: (_redact_text(str(v), grounded, ungrounded) if isinstance(v, str) else v)
                     for k, v in a.items()}
            new_actions.append(a)
        clean["actions"] = new_actions

    # de-dupe, preserve order
    seen = set()
    unique_ungrounded = [x for x in ungrounded if not (x in seen or seen.add(x))]

    clean["verified"] = len(unique_ungrounded) == 0
    clean["ungrounded_numbers"] = unique_ungrounded
    return clean
