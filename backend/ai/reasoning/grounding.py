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
  • Grounding is tolerant of representation, but the representation transform is
    TIED TO THE SIGNAL IN THE TEXT — not applied blindly. The payload stores
    money in cents and ratios as fractions; the model reasonably says "KES 9,000"
    for 900000 cents or "58%" for 0.583. So:
      – a currency-marked figure (KES/$/USD) grounds against a payload value OR
        that value ÷100 (cents → currency units);
      – a percent-marked figure (%) grounds against a payload value OR a payload
        FRACTION (|v| ≤ 1.5) ×100 (ratio → percent);
      – a plain figure grounds only against the payload value itself (± rounding).
    Why context-tied and not a blanket derivation set: the old design pre-expanded
    EVERY payload number into {÷100, ×100, rounded} forms and matched against a
    single flat set with a 1% *relative* tolerance. On a real payload (thousands
    of numbers, money in cents) that set saturated the number line — an invented
    "23%" would ground against some unrelated 2,300-cent value via ÷100, and an
    invented "KES 7,777,777" against any large figure within a 1%-of-millions
    band. Measured: ~96–99% of random fake numbers passed as "verified". Tying
    ÷100 to a currency marker and ×100 to a percent-marker-on-a-fraction, with a
    tight absolute-first tolerance, collapses those coincidences while keeping
    every legitimate rendering (see tests) grounded.
  • Sign is a representation choice too. A payload `revenue_mom_pct: -15.0` is
    correctly rendered as "down 15%", "-15%", or "fell 15%" — so matching is on
    MAGNITUDE (abs of both sides). Before the 2026-07-08 fix `_NUMBER_RE` matched
    no minus sign and only signed values were grounded, so *every* negative was
    unmatchable: "Revenue down 15%" — the single most important line an owner
    reads — was rewritten to "Revenue down [unverified]". The guard was mutilating
    the correct number it exists to protect.
  • Enforcement redacts in place rather than dropping whole sentences — the
    qualitative judgement survives; only the false digit is removed.
"""

import re

# A number is worth policing if it carries a %/currency/decimal signal or is
# reasonably large. This keeps the guard focused on the figures that actually
# mislead (prices, percentages, volumes) and off harmless counts.
_MIN_CHECKABLE_MAGNITUDE = 10.0

# "Does this output number match a payload one?" is absolute-tolerance-first:
# _ABS_TOL (0.5) absorbs the model rounding a value to the nearest whole unit
# (1234.56 → "1,235", 58.3 → "58%") regardless of magnitude, while _REL_TOL
# (0.5%) only widens the band for genuinely large figures where float/format
# noise scales up. Crucially the band is NARROW: it must accept 58 for 58.3 but
# reject 23 for 25. The old 1%-relative-only band, combined with a derivation
# set that pre-multiplied every number by 100 and ÷100, is what let unrelated
# figures ground each other — see module docstring.
_ABS_TOL = 0.5
_REL_TOL = 0.005

# A payload value only stands in for a percentage via ×100 if it is plausibly a
# ratio/fraction in the first place. Above this it's a count or an amount, not a
# 0–1 proportion, and ×100 would be a coincidence not a representation.
_FRACTION_MAX = 1.5

# A percent-marked figure ("47%") is the highest-stakes thing a model can invent
# and the hardest to police: percentages and small counts share the 0–100 band,
# so a bare magnitude match lets a fabricated "47%" ground against an unrelated
# "47 units". Defence: a %-figure may ONLY ground against payload values that are
# actually percentages — a value under a percent-ish key (margin_pct, food_cost_rate,
# gross_margin, delivery_share, …) or a fraction ×100 — never an arbitrary count.
# Keys are matched on these stems.
_PCT_KEY_RE = re.compile(r"pct|percent|margin|rate|share|ratio", re.IGNORECASE)

_REDACTION = "[unverified]"

# Matches: 1,234.56  |  1234  |  25%  |  KES 9,000  |  $12.50  |  -15% — capturing
# the numeric core and any %/currency context so we can decide if it's "checkable".
#
# The leading minus is only consumed when it isn't preceded by a word char, "."
# or "," — so a real negative ("down -15%", "(-15%)") is read as -15, while a
# hyphen doing other work is not: "2026-07-08" still reads 2026/07/08 and the
# range "15-20%" still reads 15 and 20, not 15 and -20.
_NUMBER_RE = re.compile(
    r"(?P<cur>KES\s*|\$\s*|USD\s*)?"
    r"(?P<num>(?<![\w.,])-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?))"
    r"(?P<pct>\s*%)?",
    re.IGNORECASE,
)


def collect_payload_numbers(payload) -> set:
    """
    Every numeric value that literally appears in the payload (raw, no derived
    representations). Container lengths are intentionally excluded — see _walk().
    Representation transforms (÷100, ×100) are NOT baked in here; they're applied
    at match time, tied to the text's own currency or percent signal, so an
    invented figure can't ground itself against an unrelated value via a
    coincidental transform. See module docstring.

    `payload` may be a dict/list (walked) OR the exact JSON STRING that was sent
    to the model. The string form is the faithful definition of "grounded": a
    model can only truthfully cite a figure that was in its input, so grounding
    against the truncated/whitelisted prompt text — not the full pre-shrink dict —
    is both more correct AND far less collision-prone (the full payload's deep
    per-item detail arrays, which the model never saw, are exactly what used to
    saturate the grounded set). The narrator passes the shrunk string; the unit
    tests pass dicts. Both are supported.
    """
    return _collect_typed(payload)[0]


# Matches a JSON `"key": number` pair so we can read the key that labels a value
# even when grounding against the raw prompt STRING (not a parsed dict).
_JSON_KV_RE = re.compile(r'"(?P<key>[^"]+)"\s*:\s*(?P<val>-?\d+(?:\.\d+)?)')


def _collect_typed(payload) -> tuple[set, set]:
    """
    Return (all_numbers, percent_role_numbers). `percent_role_numbers` are those
    whose labelling key looks like a percentage/ratio (see _PCT_KEY_RE); a
    %-marked model figure is only allowed to ground against these (or a fraction
    ×100). Everything else — currency, counts, volumes — grounds against
    all_numbers. Accepts a dict/list (walked, key-aware) or the JSON string the
    model saw (regex over `"key": value` pairs, plus every bare number).
    """
    all_nums: set = set()
    pct_nums: set = set()
    if isinstance(payload, str):
        for m in _NUMBER_RE.finditer(payload):
            try:
                all_nums.add(float(m.group("num").replace(",", "")))
            except (ValueError, AttributeError):
                pass
        for m in _JSON_KV_RE.finditer(payload):
            if _PCT_KEY_RE.search(m.group("key")):
                try:
                    pct_nums.add(float(m.group("val")))
                except ValueError:
                    pass
        return all_nums, pct_nums
    _walk(payload, all_nums, pct_nums, parent_key=None)
    return all_nums, pct_nums


def _walk(obj, out: set, pct_out: set, parent_key) -> None:
    if isinstance(obj, bool):
        return  # bool is an int subclass — never treat True/False as a figure
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        if parent_key and _PCT_KEY_RE.search(str(parent_key)):
            pct_out.add(float(obj))
        return
    if isinstance(obj, dict):
        # Deliberately do NOT ground container lengths. Tracking len() at every
        # depth let a fabricated figure pass whenever it equalled some unrelated
        # collection's size — an invented "25%" grounding against a 25-item order
        # list. Legitimate small counts ("your 3 channels") already pass via the
        # _MIN_CHECKABLE_MAGNITUDE carve-out, and counts that actually matter
        # (total_items, etc.) appear as explicit numeric fields, which ARE
        # grounded. A false redact costs UX; a false pass costs trust.
        for k, v in obj.items():
            _walk(v, out, pct_out, parent_key=k)
        return
    if isinstance(obj, (list, tuple)):
        # list items inherit the key that labelled the list (e.g. "margins": [..])
        for v in obj:
            _walk(v, out, pct_out, parent_key=parent_key)
        return
    # numeric-looking strings ("58.3", "25%") count as grounded too
    if isinstance(obj, str):
        m = _NUMBER_RE.fullmatch(obj.strip())
        if m:
            try:
                val = float(m.group("num").replace(",", ""))
            except ValueError:
                return
            out.add(val)
            if parent_key and _PCT_KEY_RE.search(str(parent_key)):
                pct_out.add(val)


def _close(a: float, b: float) -> bool:
    """Absolute-first tolerance: ±0.5 always (absorbs whole-unit rounding at any
    magnitude), widening to ±0.5% only for large figures. Narrow enough that 58
    grounds 58.3 but 23 never grounds 25."""
    return abs(a - b) <= max(_ABS_TOL, _REL_TOL * max(abs(a), abs(b), 1.0))


def _is_grounded(value: float, has_pct: bool, has_cur: bool,
                 all_nums: set, pct_nums: set) -> bool:
    """
    Is `value` (as written by the model) a faithful rendering of some payload
    number? Matching is on magnitude, and the allowed representation transform is
    dictated by the text's own signal:
      • percent %   — ONLY a percent-role payload value (see _collect_typed), or
                      any payload FRACTION ×100 (ratio → percent). A %-figure may
                      NOT ground against an arbitrary same-magnitude count — that
                      is the collision that let fabricated percentages through.
      • currency $  — a payload value itself, or that value ÷100 (cents → units).
      • plain       — the literal payload value (± rounding) only.
    """
    av = abs(value)

    if has_pct:
        for p in pct_nums:
            ap = abs(p)
            if _close(av, ap) or _close(av, round(ap)):
                return True
        for p in all_nums:  # a fraction rendered as a percent (0.583 → "58%")
            ap = abs(p)
            if ap <= _FRACTION_MAX and _close(av, ap * 100.0):
                return True
        return False

    for p in all_nums:
        ap = abs(p)
        if _close(av, ap) or _close(av, round(ap)):
            return True
        if has_cur and (_close(av, ap / 100.0) or _close(av, round(ap / 100.0))):
            return True
    return False


def _redact_text(text: str, all_nums: set, pct_nums: set, ungrounded_out: list) -> str:
    if not text:
        return text

    def repl(m: re.Match) -> str:
        num_str = m.group("num")
        has_pct = bool(m.group("pct"))
        has_cur = bool(m.group("cur"))
        checkable = has_pct or has_cur or "." in num_str
        try:
            value = float(num_str.replace(",", ""))
        except ValueError:
            return m.group(0)
        # abs(), not the raw value: a bare "-500" is a large figure worth
        # policing, but `-500 < 10` would have waved it straight through.
        if not checkable and abs(value) < _MIN_CHECKABLE_MAGNITUDE:
            return m.group(0)  # bare small integer — not policed
        if _is_grounded(value, has_pct, has_cur, all_nums, pct_nums):
            return m.group(0)  # correct figure — leave it
        ungrounded_out.append(m.group(0).strip())
        return _REDACTION

    return _NUMBER_RE.sub(repl, text)


def redact_free_text(text: str, grounded_numbers: set) -> tuple:
    """
    Redact ungrounded numbers from a plain string. Companion to verify(), which
    works on the structured {headline, priorities, actions} narrative dict; this
    is for callers whose LLM output is free text — e.g.
    ai/whatsapp/orchestrator.py's tool-calling reply, where a hallucinated figure
    would otherwise reach the owner unchecked. Returns (clean_text, ungrounded).
    """
    ungrounded: list = []
    # Free-text path (short WhatsApp tool outputs): no key context to type
    # percentages, and the number set is tiny so collisions aren't a concern —
    # treat the accumulated set as both the general and percent-eligible pool,
    # preserving the pre-typing behaviour for this caller.
    clean = _redact_text(str(text or ""), grounded_numbers, grounded_numbers, ungrounded)
    seen = set()
    unique = [x for x in ungrounded if not (x in seen or seen.add(x))]
    return clean, unique


def verify(narrative: dict, payload) -> dict:
    """
    Return a copy of `narrative` with every ungrounded number in its text fields
    redacted, plus grounding metadata:
      verified           : True when no ungrounded numbers were found
      ungrounded_numbers : the offending figures (as written by the model)

    Never raises and never drops the qualitative content — only the false digits.
    """
    all_nums, pct_nums = _collect_typed(payload)
    ungrounded: list = []

    clean = dict(narrative)
    if "headline" in clean:
        clean["headline"] = _redact_text(str(clean["headline"]), all_nums, pct_nums, ungrounded)
    if isinstance(clean.get("priorities"), list):
        clean["priorities"] = [_redact_text(str(p), all_nums, pct_nums, ungrounded) for p in clean["priorities"]]
    if isinstance(clean.get("actions"), list):
        new_actions = []
        for a in clean["actions"]:
            if isinstance(a, dict):
                a = {k: (_redact_text(str(v), all_nums, pct_nums, ungrounded) if isinstance(v, str) else v)
                     for k, v in a.items()}
            new_actions.append(a)
        clean["actions"] = new_actions

    # de-dupe, preserve order
    seen = set()
    unique_ungrounded = [x for x in ungrounded if not (x in seen or seen.add(x))]

    clean["verified"] = len(unique_ungrounded) == 0
    clean["ungrounded_numbers"] = unique_ungrounded
    return clean
