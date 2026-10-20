"""
backend/owner/settings.py — the owner's thresholds, in one place (docs/v2/SPEC.md §3.2, sprint S1.1).

One source of truth for every business rule an engine used to hard-code:
  * DEFAULTS — what an owner who has chosen nothing gets (today's constants, so moving an engine from a
    module constant to settings changes no number; the one documented exception is the food-cost ceiling,
    which was 35 in profit/pricing and 40 in menu and is unified at 35 in S1.2);
  * FIELDS — each setting's allowed range and the sentence the owner is asked, in owner words (§3.4);
  * get_settings(db, restaurant_id) — what engines call. Never writes. No row = the defaults;
  * update_settings(...) — the ONLY write path: validates, writes a complete row, audits every change.

Engines take a `settings` argument (default None → DEFAULTS) so existing callers and tests keep working.

Units. Inside the backend money is integer cents (cash_tolerance_cents, price_step_cents) and percentages
are plain percent numbers (35.0, not 0.35). The API edge speaks the owner's units — KES, not cents — via
FieldSpec.scale (stored = api × scale).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace, fields as dataclass_fields
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import models
from time_utils import utcnow

logger = logging.getLogger("owner.settings")


@dataclass(frozen=True)
class Settings:
    # Costs and margins
    food_cost_target_pct: float = 35.0       # ingredients, % of sales, at most
    prime_cost_target_pct: float = 62.0      # ingredients + wages, % of sales, at most
    margin_floor_pct: float = 40.0           # below this a dish is "priced too low"
    margin_target_pct: float = 55.0
    popular_cutoff: float = 0.70             # × the average dish's units sold
    # Stock and cash
    missing_stock_flag_pct: float = 3.0
    cash_tolerance_cents: int = 20_000       # KES 200 ...
    cash_tolerance_pct: float = 1.0          # ... or 1% of takings, whichever is larger
    # Delivery
    commission_uber_eats_pct: float = 25.0
    commission_glovo_pct: float = 25.0
    commission_bolt_food_pct: float = 20.0
    # Prices
    offer_size_pct: float = 10.0
    offer_lift_pct: float = 30.0
    max_raise_pct: float = 15.0
    price_step_cents: int = 500              # suggested prices round UP to a KES 5 step
    price_sensitivity: float = -0.7
    # Staff
    labour_target_pct: float = 30.0          # placeholder default, not from the notes — confirm at onboarding
    overtime_after_hours: float = 8.0
    # Alerts and permits
    urgent_alerts_per_day: int = 5
    quiet_hours_start: int = 22
    quiet_hours_end: int = 7
    licence_warning_days: int = 14
    # Money (S3.3)
    expense_spike_pct: float = 25.0          # a cost this far above its usual (3-month average) is flagged
    bill_reserve_cents: int = 0              # cash the owner keeps aside for bills: the bill radar's opening position
    mpesa_match_minutes: int = 10            # how far apart a sale and its M-Pesa payment may be and still count as the same (S6.2)

    def commission_rate(self, channel: str) -> float:
        """Delivery commission as a fraction (0.25) for a DeliveryChannel value; 0 for channels without one."""
        return {"uber_eats": self.commission_uber_eats_pct, "glovo": self.commission_glovo_pct,
                "bolt_food": self.commission_bolt_food_pct}.get(channel, 0.0) / 100.0

    @property
    def commissions(self) -> dict[str, float]:
        """{channel: fraction} for every platform that charges one."""
        return {ch: self.commission_rate(ch) for ch in ("uber_eats", "glovo", "bolt_food")}


DEFAULTS = Settings()
_ATTRS = [f.name for f in dataclass_fields(Settings)]


@dataclass(frozen=True)
class FieldSpec:
    key: str            # API name
    attr: str           # Settings attribute / column name
    group: str
    label: str
    question: str       # asked in onboarding, in owner words
    unit: str
    minimum: float      # allowed range, in API units
    maximum: float
    step: float
    kind: str = "float"  # "float" | "int"
    scale: int = 1       # stored = api × scale  (KES → cents = 100)
    hint: str = ""       # one line under the control

    @property
    def default(self):
        return self.to_api(getattr(DEFAULTS, self.attr))

    def to_api(self, stored):
        value = stored / self.scale
        return int(round(value)) if self.kind == "int" else float(value)

    def to_stored(self, api_value):
        if self.kind == "int":
            return int(round(api_value * self.scale))
        return float(api_value) * self.scale if self.scale != 1 else float(api_value)


def _f(key, group, label, question, unit, lo, hi, step, *, attr=None, kind="float", scale=1, hint="") -> FieldSpec:
    return FieldSpec(key=key, attr=attr or key, group=group, label=label, question=question, unit=unit,
                     minimum=lo, maximum=hi, step=step, kind=kind, scale=scale, hint=hint)


FIELDS: list[FieldSpec] = [
    _f("food_cost_target_pct", "Costs and margins", "Ingredient cost target",
       "Out of every KES 100 you sell, how much should ingredients cost at most?", "%", 20, 50, 1),
    _f("prime_cost_target_pct", "Costs and margins", "Ingredients + wages target",
       "Out of every KES 100 you sell, how much can ingredients plus wages cost at most?", "%", 40, 80, 1),
    _f("margin_floor_pct", "Costs and margins", "Lowest share you keep on a dish",
       "What is the lowest share of a dish's price you are willing to keep after its ingredients?", "%", 20, 70, 1),
    _f("margin_target_pct", "Costs and margins", "Share you would like to keep on a dish",
       "What share of a dish's price would you like to keep after its ingredients?", "%", 30, 80, 1),
    _f("popular_cutoff", "Costs and margins", "What counts as a popular dish",
       "How well must a dish sell, compared with your average dish, to count as popular?", "× average", 0.5, 1.0, 0.05),
    _f("missing_stock_flag_pct", "Stock and cash", "Missing stock we flag",
       "How much more stock than your recipes explain should we accept before flagging missing stock?", "%", 1, 10, 0.5),
    _f("cash_tolerance_kes", "Stock and cash", "Cash count difference we accept",
       "How far off can a cash count be, in shillings, before we ask you to check it?", "KES", 0, 2000, 50,
       attr="cash_tolerance_cents", kind="int", scale=100),
    _f("cash_tolerance_pct", "Stock and cash", "Cash count difference we accept (share of takings)",
       "We use the larger of the shilling amount and this share: what share of the shift's cash takings can a count be off by?", "%", 0, 5, 0.5),
    _f("commission_uber_eats_pct", "Delivery", "Uber Eats commission",
       "What commission does Uber Eats take on each order?", "%", 0, 40, 1),
    _f("commission_glovo_pct", "Delivery", "Glovo commission",
       "What commission does Glovo take on each order?", "%", 0, 40, 1),
    _f("commission_bolt_food_pct", "Delivery", "Bolt Food commission",
       "What commission does Bolt Food take on each order?", "%", 0, 40, 1),
    _f("offer_size_pct", "Prices", "Offer size",
       "How big a discount are you willing to try on a dish that is selling slowly?", "%", 5, 30, 1),
    _f("offer_lift_pct", "Prices", "Extra sales you expect from an offer",
       "How many extra plates do you expect to sell when you run an offer?", "%", 0, 100, 5),
    _f("max_raise_pct", "Prices", "Biggest price rise at once",
       "What is the biggest price rise you would make in one go?", "%", 5, 30, 1),
    _f("price_step_kes", "Prices", "Price rounding step",
       "What step should suggested prices round up to, in shillings?", "KES", 1, 50, 1,
       attr="price_step_cents", kind="int", scale=100),
    _f("price_sensitivity", "Prices", "How guests react to price changes",
       "How strongly do your guests react when a price changes?",
       "", -1.2, -0.4, 0.1, hint="-1.2 means guests react a lot; -0.4 means hardly at all."),
    _f("labour_target_pct", "Staff", "Wages target",
       "Out of every KES 100 you sell, how much should wages cost at most?", "%", 15, 50, 1),
    _f("overtime_after_hours", "Staff", "Overtime starts after",
       "After how many hours in a day does overtime start?", "hours", 6, 12, 0.5),
    _f("urgent_alerts_per_day", "Alerts and permits", "Urgent alerts per day",
       "How many urgent alerts are we allowed to send you in one day?", "per day", 1, 20, 1, kind="int"),
    _f("quiet_hours_start", "Alerts and permits", "Quiet hours start",
       "From what hour of the night should we stay quiet?", "o'clock", 0, 23, 1, kind="int",
       hint="24-hour clock, Nairobi time (22 means 10 pm)."),
    _f("quiet_hours_end", "Alerts and permits", "Quiet hours end",
       "Until what hour of the morning should we stay quiet?", "o'clock", 0, 23, 1, kind="int"),
    _f("licence_warning_days", "Alerts and permits", "Licence warning",
       "How many days before a licence expires should we warn you?", "days", 7, 60, 1, kind="int"),
    _f("expense_spike_pct", "Money", "Cost increase we flag",
       "How far above your usual should a cost be, before we tell you it is going up?", "%", 10, 100, 5,
       hint="Your usual is what that cost averaged over the last three months."),
    _f("bill_reserve_kes", "Money", "Cash you keep aside for bills",
       "How much cash do you keep aside for bills?", "KES", 0, 10_000_000, 1000,
       attr="bill_reserve_cents", kind="int", scale=100,
       hint="We count it when we check whether your sales will cover the bills that fall due."),
    _f("mpesa_match_minutes", "Money", "Minutes between a sale and its M-Pesa payment",
       "How many minutes apart can a sale and its M-Pesa payment be and still count as the same one?", "minutes", 2, 60, 1, kind="int",
       hint="We match a payment on your statement to the sale with the same amount that is closest in time."),
]
BY_KEY = {f.key: f for f in FIELDS}
BY_ATTR = {f.attr: f for f in FIELDS}
assert sorted(BY_ATTR) == sorted(_ATTRS), "every Settings attribute needs exactly one FieldSpec"


class SettingsError(ValueError):
    """A rejected settings change. `field` is the API key at fault (None when several are)."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


# ── reading ──────────────────────────────────────────────────────────────────

def _row(db: Session, restaurant_id: int):
    return db.query(models.RestaurantSettings).filter(
        models.RestaurantSettings.restaurant_id == restaurant_id).first()


def _from_row(row) -> Settings:
    return Settings(**{attr: getattr(row, attr) for attr in _ATTRS})


def get_settings(db: Session, restaurant_id: int) -> Settings:
    """The restaurant's settings; DEFAULTS when the owner has chosen nothing. Never writes.

    Fails safe: if the table cannot be read (code deployed before migration 051, a database blip) the
    defaults are returned and the problem is logged — every engine calls this, so it must never be the
    reason Home or the AI pages go down. The read runs in a SAVEPOINT so that on PostgreSQL a failed
    statement does not poison the caller's transaction (same pattern as overview._source_connection).
    """
    try:
        with db.begin_nested():
            row = _row(db, restaurant_id)
    except SQLAlchemyError:
        logger.warning("restaurant_settings unreadable for restaurant %s; using defaults", restaurant_id, exc_info=True)
        return DEFAULTS
    return _from_row(row) if row else DEFAULTS


def resolve(db: Session, restaurant_id: int, settings: Settings | None = None) -> Settings:
    """What an engine calls first: the settings it was handed, else the restaurant's saved ones (else defaults).

    Passing `settings` explicitly is for the owner API and previews; passing nothing means every existing
    caller (Home, OS, reports, WhatsApp, the old dashboard) honours the owner's saved choices untouched.
    """
    return settings if settings is not None else get_settings(db, restaurant_id)


def describe(db: Session, restaurant_id: int) -> dict:
    """The settings screen payload: every field with its value, default, range and the question in owner words."""
    row = _row(db, restaurant_id)
    current = _from_row(row) if row else DEFAULTS
    out = []
    for spec in FIELDS:
        value = spec.to_api(getattr(current, spec.attr))
        out.append({
            "key": spec.key, "group": spec.group, "label": spec.label, "question": spec.question,
            "unit": spec.unit, "value": value, "default": spec.default, "min": spec.minimum,
            "max": spec.maximum, "step": spec.step, "hint": spec.hint, "is_default": value == spec.default,
        })
    return {
        "chosen": row is not None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by_user_id if row else None,
        "fields": out,
    }


def history(db: Session, restaurant_id: int, limit: int = 50) -> list[dict]:
    rows = (db.query(models.RestaurantSettingsAudit)
            .filter(models.RestaurantSettingsAudit.restaurant_id == restaurant_id)
            .order_by(models.RestaurantSettingsAudit.id.desc()).limit(limit).all())
    return [{"field": r.field, "key": BY_ATTR[r.field].key if r.field in BY_ATTR else r.field,
             "old_value": r.old_value, "new_value": r.new_value,
             "changed_by": r.changed_by_user_id, "changed_at": r.changed_at.isoformat()} for r in rows]


# ── writing ──────────────────────────────────────────────────────────────────

def _validate(changes: dict[str, Any]) -> dict[str, Any]:
    """API-unit changes → {attr: stored value}. Raises SettingsError on anything out of range."""
    if not changes:
        raise SettingsError("Nothing to change: send at least one setting.")
    stored: dict[str, Any] = {}
    for key, raw in changes.items():
        spec = BY_KEY.get(key)
        if spec is None:
            raise SettingsError(f"Unknown setting '{key}'.", key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            raise SettingsError(f"{key}: {spec.label} must be a number.", key)
        if spec.kind == "int" and float(raw) != int(raw):
            raise SettingsError(f"{key}: {spec.label} must be a whole number.", key)
        if not (spec.minimum <= raw <= spec.maximum):
            unit = f" {spec.unit}" if spec.unit else ""
            raise SettingsError(
                f"{key}: {spec.label} must be between {spec.minimum:g} and {spec.maximum:g}{unit}.", key)
        stored[spec.attr] = spec.to_stored(raw)
    return stored


def _check_together(new: Settings) -> None:
    if new.margin_floor_pct > new.margin_target_pct:
        raise SettingsError(
            f"margin_floor_pct ({new.margin_floor_pct:g}%) cannot be higher than margin_target_pct "
            f"({new.margin_target_pct:g}%): the lowest share you accept must not exceed the share you aim for.",
            "margin_floor_pct")


def update_settings(db: Session, restaurant_id: int, user_id: int | None, changes: dict[str, Any], *, commit: bool = True) -> Settings:
    """Validate and save `changes` (API units, keyed by FieldSpec.key); audit every field that changed.

    A complete row is always written (no NULL-means-default). Re-saving a value an owner already has
    writes nothing and leaves updated_at alone. Raises SettingsError; the caller maps it to a 422.

    `commit=False` only flushes: the new values are visible to everything that reads settings in this transaction, and the caller owns
    the rollback (owner/preview.py runs the engines under a proposed setting that way, inside a SAVEPOINT, and throws it away).
    """
    stored_changes = _validate(changes)
    for attempt in (1, 2):
        row = _row(db, restaurant_id)
        before = _from_row(row) if row else DEFAULTS
        after = replace(before, **stored_changes)
        _check_together(after)
        changed = [attr for attr in _ATTRS if getattr(after, attr) != getattr(before, attr)]
        now = utcnow()
        try:
            if row is None:
                row = models.RestaurantSettings(
                    restaurant_id=restaurant_id, updated_by_user_id=user_id, created_at=now, updated_at=now,
                    **{attr: getattr(after, attr) for attr in _ATTRS})
                db.add(row)
            elif changed:
                for attr in changed:
                    setattr(row, attr, getattr(after, attr))
                row.updated_by_user_id, row.updated_at = user_id, now
            for attr in changed:
                db.add(models.RestaurantSettingsAudit(
                    restaurant_id=restaurant_id, field=attr, old_value=str(getattr(before, attr)),
                    new_value=str(getattr(after, attr)), changed_by_user_id=user_id, changed_at=now))
            db.commit() if commit else db.flush()
            return after
        except IntegrityError:
            db.rollback()          # two first-saves raced on the unique restaurant_id; redo against the winner
            if attempt == 2:
                raise
    raise AssertionError("unreachable")
