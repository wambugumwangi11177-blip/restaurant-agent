"""
backend/owner/preview.py — "what would change if I moved this?" (docs/v2/SPEC.md §3.2).

The "Based on: your floor 40% · Change" sheet asks, as the owner moves a slider, how many of Home's cards a new value would change. The
answer must be the real one, so it is not estimated: the proposed settings are written inside a SAVEPOINT, Home's whole ranked card
list is composed again by the same engines that will run after a real save, and the savepoint is rolled back. Nothing is committed,
audited or left behind, a restaurant that has never saved settings stays "not chosen", and what the sheet says is, by construction,
what saving does (tests/test_s45_settings_preview.py saves afterwards and compares).
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

import models
from owner import settings as owner_settings
from owner.home import ranked_cards
from owner.states import OwnerContext, kes

SHOWN = 8            # sentences returned per group; the counts are always complete


def _by_id(cards: list[dict]) -> dict[str, dict]:
    return {c["id"]: c for c in cards}


def _stem(title: str) -> str:
    """A card's sentence with its amounts masked. A pricing card carries its price in its words ("Raise Burger on Glovo to KES 800"), so
    when a setting moves the price the card gets a new id — to the owner it is the same card with a new figure, not one that went away
    and another that appeared."""
    return re.sub(r"KES [\d,]+(?:\.\d+)?", "KES _", title)


def preview_settings(db: Session, user: models.User, restaurant: models.Restaurant, changes: dict) -> dict:
    """The cards that would appear, go away or change their figure under `changes` (API units). Raises SettingsError on a bad value."""
    before_settings = owner_settings.get_settings(db, restaurant.id)
    before = _by_id(ranked_cards(OwnerContext(db, user, restaurant, before_settings)))
    saved_points = db.begin_nested()
    try:
        after_settings = owner_settings.update_settings(db, restaurant.id, user.id, changes, commit=False)
        after = _by_id(ranked_cards(OwnerContext(db, user, restaurant, after_settings)))
    finally:
        saved_points.rollback()
        db.expire_all()

    asked = []
    for key, to in changes.items():
        spec = owner_settings.BY_KEY[key]
        was = spec.to_api(getattr(before_settings, spec.attr))
        if was != to:
            asked.append({"key": key, "label": spec.label, "unit": spec.unit, "from": was, "to": to})

    sentence = lambda c: c["title"]                                                              # noqa: E731
    new = [after[i] for i in after if i not in before]
    gone = [before[i] for i in before if i not in after]
    figures = [sentence(after[i]) for i in after if i in before and kes(after[i].get("impact_cents_month") or None) != kes(before[i].get("impact_cents_month") or None)]
    for card in list(new):                                                                       # the same card under a new price
        twin = next((g for g in gone if g["domain"] == card["domain"] and _stem(g["title"]) == _stem(card["title"])), None)
        if twin is not None:
            gone.remove(twin)
            new.remove(card)
            figures.append(sentence(card))
    appear, disappear = [sentence(c) for c in new], [sentence(c) for c in gone]
    return {"changes": asked, "cards_now": len(before), "cards_after": len(after),
            "appear": appear[:SHOWN], "disappear": disappear[:SHOWN], "figures": figures[:SHOWN],
            "changed": len(appear) + len(disappear) + len(figures)}
