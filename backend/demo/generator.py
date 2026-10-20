"""
backend/demo/generator.py — the demo restaurant, written through the ORM (docs/v2/SPEC.md §6, S2.1).

    build(db, owner_email, owner_password, seed=..., now=..., days=120)  ->  DemoSummary

One tenant "Demo Restaurant", two branches, 120 days of trading, about KES 100,000 a week per branch. The rows are what a
real restaurant on LEVIII would have — orders with items and kitchen times, order-time stock deductions, deliveries,
weekly stock counts, store-to-kitchen handovers, shifts, drawer counts per shift, bookings, guests — so the real engines
run on it and the demo needs no maths of its own.

  Determinism   Every random draw comes from `random.Random("<seed>|<branch>|<date>|<stream>")`, never the global RNG: the
                same seed gives the same rows. A calendar day looks the same whenever you re-seed it (weekday patterns
                follow the real calendar); only the stock simulation depends on where the 120-day window starts.
  Relative      Dates are relative to `now`, so the demo never looks stale; today is partial (nothing in the future).
  Honest        This is illustrative data. It never writes a payment reference, a real phone number or a real person's name.
  Baseline      `plant=()` writes the baseline distribution only; S2.2 adds the planted scenarios of figure 6.1.

Money is integer cents. Times are stored as naive UTC; the day the owner sees is the Nairobi day (UTC+3).
"""
from __future__ import annotations

import math
import random
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import auth
import models
from demo import catalog as cat
from demo.wipe import wipe_demo
from tenant_provisioning import DEMO_NAME, ensure_demo_restaurant
from time_utils import EAT_OFFSET, eat_date, utcnow

DEFAULT_SEED = 20261015
DEFAULT_DAYS = 120
STAFF_EMAILS = {
    "manager": ("manager@demo-restaurant.example", models.StaffRole.MANAGER),
    "storekeeper": ("store@demo-restaurant.example", models.StaffRole.STOCKKEEPER),
    "kitchen": ("kitchen@demo-restaurant.example", models.StaffRole.KITCHEN),
}
WEEKLY_ORDERS = cat.WEEKLY_SALES_TARGET_CENTS / cat.average_order_cents()
PROTEINS_HANDED_OVER = ("chicken", "beef", "beef_mince", "goat", "tilapia", "rice")
TABLE_CAPACITIES = (2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 8, 8, 10)
# staff index -> the two weekdays (Mon=0) they are off; nobody is ever off on Friday or Saturday
OFF_DAYS = ((0, 3), (1, 2), (0, 2), (1, 3), (0, 6), (2, 6), (3, 6), (1, 6))
SHIFT_STARTS = (8, 8, 16, 8, 16, 8, 16, 8)          # per staff index: day (08:00) or evening (16:00), 7 h
SHIFT_HOURS = 7.0
# Figure 6.1 scenarios the generator plants (docs/v2/figures/scenarios.md). P1 (Quarter chicken 400/260), P11 (the four
# menu kinds) and P16 (till-rung M-Pesa sales without a receipt) hold by construction of the catalog and the baseline.
# P8 (M-Pesa statement), P9 (gas) and P10 (rent) are planted by their own phases. Planted on the owner's default branch (Westlands)
# unless the scenario is about the comparison of the two (P14).
PLANTS = ("P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P12", "P13", "P14", "P15")
P2_DAYS = 21                    # Chips charged KES 270 on the till (menu 300) for three weeks (the engine looks at 14 days from its own anchor)
P3_GLOVO_BURGER_BOOST = 8.0     # Glovo guests order burgers far more than the average guest does
P4_AFTERNOON_MIX = {"Quarter chicken": 8.0, "Burger": 4.0, "Beef stew": 3.0, "Beef fry": 3.0, "Chicken burger": 3.0, "Chicken wings": 3.0,
                    "Chai (milk tea)": 0.3, "Nyama choma (goat)": 0.05, "Pilau": 0.3, "Samosa (2)": 0.5, "Mandazi (3)": 0.5, "Beer": 0.3,
                    "Whisky (shot)": 0.0}
P5_EXTRA_BEEF_SHARE = 0.33      # the kitchen draws a third more beef than the sales explain (scaled to the demo, see PROGRESS)
P5_DAYS = 28
P6_HANDOVER = (4.0, 3.8)        # store says 4.0 kg of beef, the kitchen counts 3.8 kg (scaled from 40 / 38)
P7_SHORT_CENTS = (45_000, 65_000)
P8_DAYS = 14                    # the statement covers the last two weeks of M-Pesa sales
P8_MISSING = 3                  # three M-Pesa sales the statement never shows
P8_GROUPS = 2                   # and two pairs of sales the guests paid with one payment
P12_OPEN_HOUR_OUT = 19          # chips are out from 19:00 Nairobi time
P12_SALES_FACTOR = 0.5
P13_RATIO = 56 / 60             # Kenchic delivers 56 of every 60 (ratio kept; the quantities are the demo's own)
P15_SUPPLIER = "Ngong Charcoal Traders"
P9_GAS_CENTS = (1_460_000, 1_410_000, 1_430_000, 1_860_000)    # KES 14,600 · 14,100 · 14,300 in the three months before, 18,600 this month so far (+29.8%)
P10_DAYS_AHEAD = 3                                            # the rent falls due this many days from today (the 4th, on the day figure 6.1 draws)
APPROVED_PRICE_CHANGES = {"Ugali sukuma": (25_000, 20), "Chicken wings": (55_000, 41)}   # (old price, days ago approved); the menu holds the new price


def local_utc(day: date, hour: int, minute: int = 0) -> datetime:
    """A Nairobi wall-clock time as a naive-UTC datetime (the way every DateTime column stores it)."""
    return datetime(day.year, day.month, day.day, hour, minute) - EAT_OFFSET


def statement_window(now: datetime) -> tuple[datetime, datetime]:
    """The span of the demo owner's M-Pesa statement: whole Nairobi days, from midnight P8_DAYS ago to 45 minutes before `now`.

    An export is for days, and the matcher reads it as days (coverage starts at midnight Nairobi of the first payment's day, S6.2 decision b). A start
    of `now - 14 days` moves through the day, and a sale on the first day earlier than the hour of the build was then left off the statement yet
    counted as covered: the gap read 4 instead of the planted 3 after about noon in Nairobi.
    """
    return local_utc(eat_date(now - timedelta(days=P8_DAYS)), 0), now - timedelta(minutes=45)


@dataclass
class Guest:
    name: str
    phone: str
    weight: float
    lapses_on: date | None


@dataclass
class BranchState:
    spec: dict
    index: int
    restaurant: models.Restaurant
    tables: list = field(default_factory=list)
    menu: dict = field(default_factory=dict)         # dish name -> MenuItem
    inv: dict = field(default_factory=dict)          # ingredient key -> InventoryItem
    suppliers: dict = field(default_factory=dict)    # supplier key -> Supplier
    staff: list = field(default_factory=list)        # [(StaffMember, hourly_rate, index)]
    guests: list = field(default_factory=list)
    open_pos: list = field(default_factory=list)     # purchase orders placed, not yet delivered
    reorder: dict = field(default_factory=dict)      # ingredient key -> (reorder point, par)
    week_usage: dict = field(default_factory=dict)   # ingredient key -> usage since the last waste movement
    min_stock: dict = field(default_factory=dict)    # ingredient key -> lowest running quantity seen (for the tests)


@dataclass
class DemoSummary:
    tenant_id: int
    restaurant_ids: list
    seed: int
    now: datetime
    days: int
    counts: dict
    weekly_sales_kes: dict
    min_stock: dict
    wiped: dict
    planted: dict = field(default_factory=dict)       # scenario id -> what was planted (a date or a note), None if it could not be

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("tenant_id", "restaurant_ids", "seed", "days", "counts", "weekly_sales_kes", "planted", "wiped")}


class DemoBuilder:
    def __init__(self, db, *, seed: int = DEFAULT_SEED, now: datetime | None = None, days: int = DEFAULT_DAYS,
                 plant: tuple = PLANTS):
        self.db = db
        self.seed = seed
        self.now = (now or utcnow()).replace(microsecond=0)
        self.days = days
        self.plant = tuple(plant)
        self.today = eat_date(self.now)
        self.first_day = self.today - timedelta(days=days - 1)
        self.users: dict[str, models.User] = {}
        self.branches: list[BranchState] = []
        self.sales_cents: dict[str, int] = {}
        self.counts: dict[str, int] = {}
        self.planted: dict[str, str | None] = {}
        self._p7_days = self._last_tuesday_evenings(4) if "P7" in self.plant else set()
        self._p12_day = self._holiday_tuesday() if "P12" in self.plant else None
        if "P12" in self.plant:
            self.planted["P12"] = self._p12_day.isoformat() if self._p12_day else None

    def planting(self, scenario: str, b: "BranchState") -> bool:
        """Scenarios about one restaurant are planted on the owner's default branch (Westlands)."""
        return scenario in self.plant and b.index == 0

    def _last_tuesday_evenings(self, n: int) -> set:
        """The latest `n` Tuesdays whose evening drawer count is already complete at `now`."""
        found, day = [], self.today
        while len(found) < n and day >= self.first_day:
            if day.weekday() == 1 and local_utc(day, 23) + timedelta(minutes=20) <= self.now:
                found.append(day)
            day -= timedelta(days=1)
        return set(found)

    def _holiday_tuesday(self) -> date | None:
        """The most recent Tuesday in the window that is a Kenyan public holiday (the same data the demand forecast uses)."""
        from ai.simulation.signals import holiday_provider
        day = self.today - timedelta(days=1)
        while day >= self.first_day:
            if day.weekday() == 1 and holiday_provider(day):
                return day
            day -= timedelta(days=1)
        return None

    # ── helpers ──────────────────────────────────────────────────────────────
    def rng(self, *parts) -> random.Random:
        return random.Random("|".join([str(self.seed), *map(str, parts)]))

    def _count(self, name: str, n: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + n

    def _past(self, when: datetime) -> bool:
        return when <= self.now

    # ── entry point ──────────────────────────────────────────────────────────
    def build(self, owner_email: str, owner_password: str) -> DemoSummary:
        db = self.db
        ensure_demo_restaurant(db, owner_email, owner_password)
        tenant = db.query(models.Tenant).filter(models.Tenant.name == DEMO_NAME).one()
        owner = db.query(models.User).filter(models.User.email == owner_email).one()
        self._branches_and_group(tenant)
        wiped = wipe_demo(db, tenant, commit=False)
        self._users(tenant)
        for b in self.branches:
            self._setup_branch(b)
        for b in self.branches:
            self._simulate(b)
            self._future(b)
            self._ledger(b)
        self._plant_after(owner)
        self._ideas_and_activity(owner)
        self._owner_settings(owner)
        owner.active_restaurant_id = self.branches[0].restaurant.id
        db.commit()
        weekly = {b.spec["key"]: round(self.sales_cents.get(b.spec["key"], 0) / 100 / (self.days / 7), 2) for b in self.branches}
        return DemoSummary(tenant.id, [b.restaurant.id for b in self.branches], self.seed, self.now, self.days,
                           dict(sorted(self.counts.items())), weekly,
                           {b.spec["key"]: dict(b.min_stock) for b in self.branches}, wiped, self.planted)

    # ── tenant, branches, people ─────────────────────────────────────────────
    def _branches_and_group(self, tenant: models.Tenant) -> None:
        db = self.db
        org = db.query(models.Organization).filter(models.Organization.tenant_id == tenant.id).first()
        if org is None:
            org = models.Organization(tenant_id=tenant.id, name="Demo Restaurant Group")
            db.add(org)
            db.flush()
        region = db.query(models.Region).filter(models.Region.organization_id == org.id).first()
        if region is None:
            region = models.Region(organization_id=org.id, name="Nairobi")
            db.add(region)
            db.flush()
        existing = {r.name: r for r in db.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).all()}
        for index, spec in enumerate(cat.BRANCHES):
            r = existing.get(spec["name"])
            if r is None and index == 0:
                r = min(existing.values(), key=lambda x: x.id)      # the restaurant ensure_demo_restaurant created
                r.name = spec["name"]
            if r is None:
                r = models.Restaurant(tenant_id=tenant.id, name=spec["name"], address=spec["address"])
                db.add(r)
            r.address, r.latitude, r.longitude = spec["address"], spec["lat"], spec["lng"]
            r.organization_id, r.region_id = org.id, region.id
            db.flush()
            self.branches.append(BranchState(spec=spec, index=index, restaurant=r))

    def _users(self, tenant: models.Tenant) -> None:
        """Staff logins for the demo's store, kitchen and floor. They get a random password nobody knows: the demo
        is explored from the owner's login; these rows exist so counts and handovers have a person on them."""
        for key, (email, staff_role) in STAFF_EMAILS.items():
            user = self.db.query(models.User).filter(models.User.email == email).first()
            if user is None:
                user = models.User(tenant_id=tenant.id, email=email, role=models.Role.STAFF, staff_role=staff_role,
                                   hashed_password=auth.get_password_hash(secrets.token_urlsafe(32)), is_active=True)
                self.db.add(user)
                self.db.flush()
            self.users[key] = user

    def _setup_branch(self, b: BranchState) -> None:
        db, rid, spec = self.db, b.restaurant.id, b.spec
        for n in range(spec["tables"]):
            t = models.Table(restaurant_id=rid, table_number=n + 1, capacity=TABLE_CAPACITIES[n % len(TABLE_CAPACITIES)])
            db.add(t)
            b.tables.append(t)
        for key, s in cat.SUPPLIERS.items():
            sup = models.Supplier(restaurant_id=rid, name=s["name"], avg_lead_days=s["lead_days"], reliability_score=100.0,
                                  contact_phone="", notes="Illustrative demo supplier")
            db.add(sup)
            b.suppliers[key] = sup
        db.flush()
        usage_scale = WEEKLY_ORDERS * spec["scale"] / 7
        per_order = cat.BASKET_MEAN_LINES * cat.LINE_MEAN_QTY
        total_w = sum(d.weight for d in cat.MENU)
        for ing in cat.INGREDIENTS:
            daily = usage_scale * per_order * sum(d.weight * d.recipe.get(ing.key, 0) for d in cat.MENU) / total_w
            lead = cat.SUPPLIERS[ing.supplier]["lead_days"]
            base = daily * (lead + 4)
            reorder = max(base + 3 * math.sqrt(base), ing.pack * 0.5)        # cover for lead time, a late truck and a busy weekend
            par = reorder + max(daily * 5, ing.pack)
            factor = spec["p14_cost_factor"] if "P14" in self.plant else spec["cost_factor"]
            cost = round(ing.cost_cents * factor)
            item = models.InventoryItem(restaurant_id=rid, item_name=ing.name, unit=ing.unit, quantity=round(par * 0.92, 2),
                                        cost_per_unit_cents=cost, low_stock_threshold=math.ceil(reorder * 0.6), par_level=round(par, 1),
                                        expiry_days=ing.shelf_days, default_supplier_id=b.suppliers[ing.supplier].id)
            db.add(item)
            b.inv[ing.key] = item
            b.reorder[ing.key] = (reorder, par)
            b.week_usage[ing.key] = 0.0
            b.min_stock[ing.key] = item.quantity
        db.flush()
        for dish in cat.MENU:
            cost = round(sum(q * b.inv[k].cost_per_unit_cents for k, q in dish.recipe.items()))
            item = models.MenuItem(restaurant_id=rid, name=dish.name, category=dish.category, price=dish.price_cents,
                                   cost_price=cost, is_available=True, prep_station=dish.station,
                                   avg_prep_minutes=dish.prep_minutes, description="")
            db.add(item)
            b.menu[dish.name] = item
        db.flush()
        for dish in cat.MENU:
            for k, q in dish.recipe.items():
                db.add(models.MenuIngredient(menu_item_id=b.menu[dish.name].id, inventory_item_id=b.inv[k].id,
                                             quantity_per_serving=q, is_critical=k not in ("lemons", "lettuce", "cheese")))
        for i, (name, title, rate, _shifts) in enumerate(cat.STAFF):
            m = models.StaffMember(restaurant_id=rid, name=name, role_title=title, hourly_rate=rate, is_active=True)
            db.add(m)
            b.staff.append((m, rate, i))
        db.flush()
        b.guests = self._guests(b)
        self._count("tables", len(b.tables))
        self._count("menu_items", len(b.menu))
        self._count("inventory_items", len(b.inv))
        self._count("suppliers", len(b.suppliers))
        self._count("staff_members", len(b.staff))

    def _guests(self, b: BranchState) -> list[Guest]:
        rng = self.rng(b.spec["key"], "guests")
        guests = []
        for i in range(120):
            tier = rng.random()
            weight = 4.0 if tier < 0.15 else 1.5 if tier < 0.50 else 0.4
            lapses = None
            if weight < 4.0 and rng.random() < 0.20:
                lapses = self.today - timedelta(days=rng.randint(25, 75))
            # +254 00 … is not a dialable Kenyan number on purpose: nothing in the demo can ever message a real person.
            guests.append(Guest(f"{rng.choice(cat.GUEST_NAMES)} {i + 1:03d}", f"+25400{b.index + 1}{i + 1:07d}", weight, lapses))
        return guests

    # ── the day loop ─────────────────────────────────────────────────────────
    def _simulate(self, b: BranchState) -> None:
        key = b.spec["key"]
        self.sales_cents[key] = 0
        day = self.first_day
        while day <= self.today:
            self._deliveries(b, day)
            self._shifts(b, day)
            plans = self._plan_orders(b, day)
            self._write_orders(b, day, plans)
            self._reservations(b, day)
            self._handovers(b, day)
            self._drawers(b, day)
            if day.weekday() == 6:
                self._weekly_close(b, day)
            self._reorder(b, day)
            self.db.flush()
            day += timedelta(days=1)

    # ── orders ───────────────────────────────────────────────────────────────
    def price_on(self, b: BranchState, dish: cat.Dish, day: date) -> int:
        """What the till charges for `dish` on `day`: the menu price, the price before an approved idea took effect,
        or (P2) KES 270 for Chips against a KES 300 menu price for the latest 14 days."""
        if dish.name == "Chips" and self.planting("P2", b) and day >= self.today - timedelta(days=P2_DAYS):
            return 27_000
        change = APPROVED_PRICE_CHANGES.get(dish.name)
        if change is not None and day < self.today - timedelta(days=change[1]):
            return change[0]
        return dish.price_cents

    def _weights(self, b: BranchState, day: date, daypart: str, hour: int, channel) -> list[float]:
        """Relative popularity of every dish for one order: the menu's own weights, bent by the scenarios planted here."""
        w = [d.weight for d in cat.MENU]
        if self.planting("P4", b) and daypart == "afternoon" and 15 <= hour < 17:
            w = [x * P4_AFTERNOON_MIX.get(d.name, 1.0) for x, d in zip(w, cat.MENU)]
        if self.planting("P3", b) and channel == models.DeliveryChannel.GLOVO:
            w = [x * (P3_GLOVO_BURGER_BOOST if d.name == "Burger" else 1.0) for x, d in zip(w, cat.MENU)]
        if self.planting("P12", b) and day == self._p12_day:
            # the holiday crowd orders chips until the potatoes run out at 19:00, and cannot after
            w = [(0.0 if hour >= P12_OPEN_HOUR_OUT else x * 6.0) if d.name == "Chips" else x for x, d in zip(w, cat.MENU)]
        return w

    def _plan_orders(self, b: BranchState, day: date) -> list[dict]:
        rng = self.rng(b.spec["key"], day.isoformat(), "orders")
        expected = WEEKLY_ORDERS * b.spec["scale"] * cat.WEEKDAY_FACTORS[day.weekday()] / 7
        if day.day >= 25:
            expected *= 1.06                       # payday week
        if self.planting("P12", b) and day == self._p12_day:
            expected *= P12_SALES_FACTOR           # the holiday
        n = max(4, round(expected * rng.gauss(1.0, 0.08)))
        active = [g for g in b.guests if g.lapses_on is None or day < g.lapses_on]
        parts = cat.DAYPARTS
        plans = []
        for _ in range(n):
            name, h0, h1, _share = rng.choices(parts, weights=[p[3] for p in parts])[0]
            hour, minute = rng.randrange(h0, h1), rng.randrange(0, 60)
            when = local_utc(day, hour, minute)
            if when > self.now:
                continue                           # nothing in the future
            r = rng.random()
            channel, otype = (models.DeliveryChannel.GLOVO, models.OrderType.DELIVERY) if r < 0.13 else \
                (models.DeliveryChannel.UBER_EATS, models.OrderType.DELIVERY) if r < 0.22 else \
                (models.DeliveryChannel.BOLT_FOOD, models.OrderType.DELIVERY) if r < 0.26 else \
                (models.DeliveryChannel.APP, models.OrderType.TAKEOUT) if r < 0.29 else \
                (models.DeliveryChannel.WALK_IN, models.OrderType.DINE_IN if rng.random() < 0.75 else models.OrderType.TAKEOUT)
            k = rng.choices(cat.BASKET_SIZES, weights=cat.BASKET_WEIGHTS)[0]
            picked: list[cat.Dish] = []
            pool, pw = list(cat.MENU), self._weights(b, day, name, hour, channel)
            for _line in range(k):
                i = rng.choices(range(len(pool)), weights=pw)[0]
                picked.append(pool.pop(i))
                pw.pop(i)
            lines = [(d, rng.choices(cat.LINE_QTYS, weights=cat.LINE_QTY_WEIGHTS)[0], self.price_on(b, d, day)) for d in picked]
            if self.planting("P7", b) and day in self._p7_days and hour >= 16 and channel == models.DeliveryChannel.WALK_IN:
                pay = models.PaymentMethod.CASH               # P7: the Tuesday-night crowd pays cash, so there is cash to come up short
            elif channel in (models.DeliveryChannel.GLOVO, models.DeliveryChannel.UBER_EATS, models.DeliveryChannel.BOLT_FOOD):
                pay = models.PaymentMethod.CARD
            elif channel == models.DeliveryChannel.APP:
                pay = models.PaymentMethod.MPESA
            else:
                p = rng.random()
                pay = models.PaymentMethod.CASH if p < 0.42 else models.PaymentMethod.MPESA if p < 0.80 else models.PaymentMethod.CARD
            has_guest = rng.random() < (0.28 if channel == models.DeliveryChannel.WALK_IN else 0.9)
            guest = rng.choices(active, weights=[g.weight for g in active])[0] if has_guest and active else None
            plans.append({"when": when, "daypart": name, "lines": lines, "channel": channel, "otype": otype, "pay": pay, "guest": guest,
                          "table": rng.randrange(1, b.spec["tables"] + 1) if otype == models.OrderType.DINE_IN else None,
                          "cancelled": rng.random() < 0.025, "draw": rng.random()})
        plans.sort(key=lambda p: p["when"])
        return plans

    def _station_factor(self, plan: dict, station: str, day: date, rng: random.Random) -> float:
        busy = 1.0
        if plan["daypart"] in ("lunch", "dinner") and day.weekday() >= 4:
            busy = 1.18 if station in ("grill", "fryer") else 1.08
        return max(0.5, rng.gauss(1.0, 0.2)) * busy

    def _write_orders(self, b: BranchState, day: date, plans: list[dict]) -> None:
        rng = self.rng(b.spec["key"], day.isoformat(), "prep")
        db, rid = self.db, b.restaurant.id
        manager = self.users["manager"]
        written: list[tuple[models.Order, dict]] = []
        day_used: dict[str, float] = {}
        if self.planting("P12", b) and day == self._p12_day:
            self._p12_potatoes(b, day, plans)
        for plan in plans:
            when = plan["when"]
            age_min = (self.now - when).total_seconds() / 60
            guest = plan["guest"]
            total = sum(q * price for _d, q, price in plan["lines"])
            cancelled = plan["cancelled"] and age_min > 30
            if cancelled:
                status, paid = models.OrderStatus.CANCELLED, False
            elif age_min < 8:
                status, paid = models.OrderStatus.PREP, plan["channel"] != models.DeliveryChannel.WALK_IN
            elif age_min < 22:
                status, paid = models.OrderStatus.READY, plan["channel"] != models.DeliveryChannel.WALK_IN
            else:
                status, paid = models.OrderStatus.SERVED, True
            order = models.Order(restaurant_id=rid, status=status, order_type=plan["otype"], delivery_channel=plan["channel"],
                                 payment_method=plan["pay"] if paid or status != models.OrderStatus.CANCELLED else models.PaymentMethod.PENDING,
                                 is_paid=paid, table_number=plan["table"], customer_name=guest.name if guest else "",
                                 customer_phone=guest.phone if guest else "", total=total, created_at=when)
            if status == models.OrderStatus.CANCELLED:
                order.payment_method = models.PaymentMethod.PENDING
            longest = 0.0
            if status != models.OrderStatus.CANCELLED:
                for dish, qty, price in plan["lines"]:
                    started = when + timedelta(minutes=rng.randint(1, 3))
                    minutes = round(dish.prep_minutes * self._station_factor(plan, dish.station, day, rng), 1)
                    done = started + timedelta(minutes=minutes)
                    longest = max(longest, minutes + 2)
                    item = models.OrderItem(menu_item_id=b.menu[dish.name].id, quantity=qty, unit_price=price)
                    if done <= self.now:
                        item.prep_time = models.PrepTime(station=dish.station, started_at=started, completed_at=done, actual_minutes=minutes)
                    else:
                        item.prep_time = models.PrepTime(station=dish.station, started_at=started)
                    order.items.append(item)
                if status == models.OrderStatus.SERVED:
                    order.completed_at = when + timedelta(minutes=round(longest + rng.uniform(15, 40)))
            else:
                for dish, qty, price in plan["lines"]:
                    order.items.append(models.OrderItem(menu_item_id=b.menu[dish.name].id, quantity=qty, unit_price=price))
            db.add(order)
            written.append((order, plan))
        db.flush()
        feedback_rng = self.rng(b.spec["key"], day.isoformat(), "feedback")
        for order, plan in written:
            if order.status == models.OrderStatus.CANCELLED:
                continue
            self.sales_cents[b.spec["key"]] += order.total if order.is_paid else 0
            used: dict[str, float] = {}
            for dish, qty, _price in plan["lines"]:
                for k, q in dish.recipe.items():
                    used[k] = used.get(k, 0.0) + q * qty
            for k, q in used.items():
                inv = b.inv[k]
                inv.quantity = round(inv.quantity - q, 4)
                b.week_usage[k] += q
                day_used[k] = day_used.get(k, 0.0) + q
                b.min_stock[k] = min(b.min_stock[k], inv.quantity)
                db.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.OUT, quantity=q,
                                            reason=f"Order #{order.id}", created_at=order.created_at + timedelta(minutes=1),
                                            performed_by_user_id=manager.id))
            self._count("stock_movements", len(used))
            if order.status == models.OrderStatus.SERVED and order.customer_phone and feedback_rng.random() < 0.10:
                rating = feedback_rng.choices((1, 2, 3, 4, 5), weights=(2, 4, 10, 34, 50))[0]
                db.add(models.CustomerFeedback(restaurant_id=b.restaurant.id, order_id=order.id, customer_phone=order.customer_phone,
                                               rating=rating, comment="", created_at=order.completed_at or order.created_at))
                self._count("customer_feedback")
            if order.status == models.OrderStatus.SERVED and feedback_rng.random() < 0.006:
                item = order.items[0]
                db.add(models.KitchenIncident(restaurant_id=b.restaurant.id, order_id=order.id, order_item_id=item.id,
                                              incident_type=feedback_rng.choice((models.IncidentType.REMAKE, models.IncidentType.QUALITY_ISSUE)),
                                              reason="Sent back at the pass", created_at=order.created_at + timedelta(minutes=25)))
                self._count("kitchen_incidents")
        if self.planting("P5", b) and (self.today - day).days < P5_DAYS and day_used.get("beef", 0) > 0:
            self._p5_extra_beef(b, day, day_used["beef"])
        self._count("orders", len(written))
        self._count("order_items", sum(len(o.items) for o, _p in written))
        self._count("prep_times", sum(len(o.items) for o, _p in written if o.status != models.OrderStatus.CANCELLED))

    # ── the money ledger: what the restaurant pays for (S3.1–S3.3) ───────────
    # key, monthly cents, day of month paid, is it a recurring bill, spread of the amount month to month
    # (line, cents a month, day paid, recurring bill?, spread). The spread is how far an ordinary month may stray from the usual, and it
    # is kept under 11 %: a month 11 % over against three months 11 % under is 1.25× — the owner's default "cost increase we flag" — so
    # a wider spread would make an unplanted line look like a spike on some days of the year (the demo is built relative to today).
    LEDGER = (("premises", 7_000_000, None, True, 0.0), ("kplc", 1_800_000, 20, True, 0.10), ("water", 320_000, 12, True, 0.08),
              ("garbage", 250_000, 5, True, 0.0), ("pos_internet", 450_000, 10, True, 0.0), ("security", 800_000, 1, True, 0.0),
              ("cleaning", 350_000, 8, False, 0.10), ("packaging", 480_000, 14, False, 0.10), ("marketing", 600_000, 16, False, 0.10),
              ("mpesa_charges", 180_000, 28, False, 0.10), ("staff_meals", 600_000, 27, False, 0.10), ("gas", 1_400_000, 3, False, 0.04))

    def _ledger(self, b: BranchState) -> None:
        """Four months of costs the owner entered, the bills that recur, and the licences — so the P&L, costs covered, bill radar
        and cost spikes have something to say. Plants P9 (gas +29.8%) and P10 (rent falls due in three days) on the default branch."""
        from owner.money.categories import ensure_categories
        db, rid = self.db, b.restaurant.id
        ensure_categories(db, rid)
        cats = {c.key: c for c in db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == rid)}
        rng = self.rng(b.spec["key"], "ledger")
        rent_day = (self.today + timedelta(days=P10_DAYS_AHEAD + b.index * 7)).day if "P10" in self.plant else 4
        scale = b.spec["scale"]
        first_of_month = self.today.replace(day=1)
        months = []
        month = first_of_month
        for _ in range(4):
            months.append(month)
            month = (month - timedelta(days=1)).replace(day=1)
        months.reverse()                                                    # three complete months and this one
        bills: dict[str, models.RecurringBill] = {}
        for key, cents, day, recurring, spread in self.LEDGER:
            amount = round(cents * (0.78 if (key == "premises" and b.index) else scale if key not in ("premises", "security", "garbage", "pos_internet") else 1.0))
            due = rent_day if key == "premises" else day
            if recurring:
                bill = models.RecurringBill(restaurant_id=rid, category_id=cats[key].id, name={"premises": "Rent", "kplc": "Electricity (KPLC)", "water": "Water",
                                                                                                "garbage": "Garbage collection", "pos_internet": "POS & internet",
                                                                                                "security": "Security"}[key],
                                            amount_cents=amount, frequency="monthly", due_day=due, start_on=months[0], supplier="", note="", is_active=True)
                db.add(bill)
                bills[key] = bill
        db.flush()
        for i, month in enumerate(months):
            last_day = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            for key, cents, day, recurring, spread in self.LEDGER:
                if key == "gas" and self.planting("P9", b):
                    amounts = [P9_GAS_CENTS[i]] if i < 3 else [P9_GAS_CENTS[3] // 2] * 2                  # this month: two refills so far
                    days = [day] if i < 3 else [1, 6]
                else:
                    base = round(cents * (0.78 if (key == "premises" and b.index) else scale if key not in ("premises", "security", "garbage", "pos_internet") else 1.0))
                    amounts = [round(base * (1 + rng.uniform(-spread, spread)))] if spread else [base]
                    days = [rent_day if key == "premises" else day]
                for amount, d in zip(amounts, days):
                    paid_on = month.replace(day=min(d, last_day.day))
                    if i == len(months) - 1 and key == "gas":
                        paid_on = min(paid_on, self.today)                                     # nothing dated after today
                    if paid_on > self.today:
                        continue
                    db.add(models.Expense(restaurant_id=rid, category_id=cats[key].id, amount_cents=amount, paid_on=paid_on,
                                          method="bank" if key in ("premises", "kplc") else "mpesa" if key in ("water", "mpesa_charges", "pos_internet") else "cash",
                                          supplier="", note="", bill_id=bills[key].id if key in bills else None,
                                          paid_by_user_id=self.users["manager"].id, created_at=local_utc(paid_on, 12), updated_at=local_utc(paid_on, 12)))
                    self._count("expenses")
        self._count("recurring_bills", len(bills))
        for name, issuer, days, cost in (("Single business permit", "Nairobi County", 190, 1_250_000), ("Health certificate", "Public Health Office", 11, 300_000),
                                         ("Fire safety certificate", "County Fire Service", 330, 450_000), ("Liquor licence", "County Liquor Board", 60, 3_000_000)):
            db.add(models.Licence(restaurant_id=rid, name=name, issuer=issuer, expires_on=self.today + timedelta(days=days), cost_cents=cost,
                                  document_ref=None, note="", is_active=True))
            self._count("licences")
        if b.index == 0:
            if "P9" in self.plant:
                self.planted["P9"] = f"gas KES {P9_GAS_CENTS[3] // 100:,} this month against a usual {round(sum(P9_GAS_CENTS[:3]) / 3 / 100):,}"
            if "P10" in self.plant:
                self.planted["P10"] = f"rent KES 70,000 falls due on the {rent_day}{'th' if 11 <= rent_day % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(rent_day % 10, 'th')}, {P10_DAYS_AHEAD} days from today"

    # ── planted scenarios (figure 6.1) ───────────────────────────────────────
    def _p12_potatoes(self, b: BranchState, day: date, plans: list[dict]) -> None:
        """P12: the potatoes delivery was missed, so what is on the shelf lasts exactly until 19:00 and chips are out after
        that. A stock-count adjustment at the start of the day records it (adjustments are not 'usage' for the custody check)."""
        need = sum(q * d.recipe.get("potatoes", 0) for p in plans if not p["cancelled"] for d, q, _price in p["lines"]
                   if (p["when"] + EAT_OFFSET).hour < P12_OPEN_HOUR_OUT)
        inv = b.inv["potatoes"]
        delta = round(need - inv.quantity, 3)
        if delta < 0:
            self.db.add(models.StockMovement(
                inventory_item_id=inv.id, movement_type=models.StockMovementType.ADJUST, quantity=delta,
                reason=f"stock count: only {need:.1f} kg of potatoes left - delivery missed, out of chips by {P12_OPEN_HOUR_OUT}:00",
                created_at=local_utc(day, 7, 0), performed_by_user_id=self.users["storekeeper"].id))
            inv.quantity = round(need, 4)
            self._count("stock_movements")

    def _p5_extra_beef(self, b: BranchState, day: date, used: float) -> None:
        """P5: the kitchen draws a third more beef than the day's sales explain; it is recorded as issued to the kitchen."""
        extra = round(used * P5_EXTRA_BEEF_SHARE, 3)
        at = local_utc(day, 12, 0)
        if extra <= 0 or at > self.now:
            return
        inv = b.inv["beef"]
        inv.quantity = round(inv.quantity - extra, 4)
        b.week_usage["beef"] += extra
        b.min_stock["beef"] = min(b.min_stock["beef"], inv.quantity)
        self.db.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.OUT, quantity=extra,
                                         reason="issued to kitchen", created_at=at, performed_by_user_id=self.users["kitchen"].id))
        self._count("stock_movements")

    def _upload_statement(self, owner: models.User, b: "BranchState") -> None:
        """The owner has uploaded two weeks of their M-Pesa statement, on the default branch. It is written as the CSV an export would be and read
        by the real parser (parsers/mpesa_csv.py) through the real importer, so the demo is also the test. Every M-Pesa sale has its payment a
        few minutes after the bill closed, and two pairs of sales were paid with one payment. P8 plants the problem: three M-Pesa sales are not on it."""
        from owner.mpesa_statement import import_statement
        rng = self.rng(b.spec["key"], "P8")
        rid = b.restaurant.id
        closed = lambda o: o.completed_at or o.created_at      # noqa: E731  when the bill was closed
        since, until = statement_window(self.now)
        orders = [o for o in self.db.query(models.Order).filter(
            models.Order.restaurant_id == rid, models.Order.payment_method == models.PaymentMethod.MPESA, models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED, models.Order.total > 0).order_by(models.Order.id)
            if since <= closed(o) <= until]
        plant = "P8" in self.plant
        if len(orders) < 20:
            if plant:
                self.planted["P8"] = None
            return

        def alone(o, minutes=25):                              # no other sale of the same amount near it: it can only match its own payment
            return not any(x.id != o.id and x.total == o.total and abs((closed(x) - closed(o)).total_seconds()) < minutes * 60 for x in orders)

        middle = [o for o in orders if self.now - timedelta(days=10) <= closed(o) <= self.now - timedelta(days=2) and alone(o)]
        if plant and len(middle) < P8_MISSING:
            self.planted["P8"] = None
            return
        missing = rng.sample(middle, P8_MISSING) if plant else []
        gone = {o.id for o in missing}
        groups, used = [], set(gone)
        for o in sorted(orders, key=closed):                   # two pairs of sales closed within twelve minutes of each other
            if o.id in used or len(groups) >= P8_GROUPS:
                continue
            mate = next((x for x in orders if x.id not in used and x.id != o.id and 0 < (closed(x) - closed(o)).total_seconds() <= 720), None)
            if mate and alone(o) and alone(mate):
                groups.append((o, mate))
                used.update((o.id, mate.id))
        grouped = {o.id for pair in groups for o in pair}
        payers = (("JOHN KAMAU", "1234"), ("MARY ACHIENG", "8821"), ("PETER OMONDI", "0042"), ("GRACE WANJIKU", "7710"), ("SAMUEL MUTUA", "3309"),
                  ("AMINA HASSAN", "5566"), ("DAVID KIPROP", "9013"), ("FAITH NJERI", "2468"))
        seen, rows = set(), []

        def receipt() -> str:
            while True:
                r = "S" + "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(9))
                if r not in seen:
                    seen.add(r)
                    return r

        def line(at: datetime, cents: int) -> None:
            who, tail = rng.choice(payers)
            local = at + EAT_OFFSET
            rows.append((at, f'{receipt()},{local:%Y-%m-%d %H:%M:%S},{(local - timedelta(seconds=11)):%Y-%m-%d %H:%M:%S},'
                             f'Customer Payment from 2547****{tail} - {who},Completed,"{cents / 100:,.2f}",,,Yes,Customer Payment,,,'))

        for o in orders:
            if o.id not in gone and o.id not in grouped:
                line(closed(o) + timedelta(seconds=rng.randint(5, 240)), o.total)
        for first, second in groups:                           # paid once, between the two closes, so each sale is inside the matching window
            line(closed(first) + (closed(second) - closed(first)) / 2 + timedelta(seconds=rng.randint(0, 60)), first.total + second.total)
        for n in range(2):                                     # money going out, which the check ignores
            at = self.now - timedelta(days=3 + 5 * n, hours=1)
            rows.append((at, f"{receipt()},{at + EAT_OFFSET:%Y-%m-%d %H:%M:%S},,Business Payment to KENCHIC LTD,Completed,,\"8,000.00\",,Yes,Business Payment,,,"))
        rows.sort(key=lambda r: r[0])
        text = "\n".join([f"Account Name,{b.restaurant.name} - Till", "Short Code,174379", "Account Type,Till (Buy Goods)",
                          f"Statement Period,{(since + EAT_OFFSET):%d-%m-%Y} to {(self.now + EAT_OFFSET):%d-%m-%Y}", "Currency,KES", "",
                          "Receipt No.,Completion Time,Initiation Time,Details,Transaction Status,Paid In,Withdrawn,Balance,Balance Confirmed,Reason Type,Other Party Info,Linked Transaction ID,A/C No.",
                          *(r for _at, r in rows)]) + "\n"
        result = import_statement(self.db, rid, owner.id, "mpesa-statement.csv", text.encode(), commit=False)
        self._count("mpesa_statement_lines", result["new"])
        if plant:
            self.planted["P8"] = (f"{P8_MISSING} M-Pesa sales (KES {sum(o.total for o in missing) // 100:,}) are not on the statement; "
                                  f"{len(groups)} pairs of sales were paid with one payment")

    def _plant_after(self, owner: models.User) -> None:
        """The scenarios that edit or add a few specific rows once the baseline is written."""
        b = self.branches[0]
        db, rid = self.db, self.branches[0].restaurant.id
        self._upload_statement(owner, b)              # the owner has uploaded two weeks of their statement; P8 is the three sales missing from it
        if "P2" in self.plant:
            self.planted["P2"] = f"Chips charged KES 270 (menu KES 300) from {(self.today - timedelta(days=P2_DAYS)).isoformat()}"
        if "P3" in self.plant:
            self.planted["P3"] = "Glovo guests order burgers about eight times as often"
        if "P4" in self.plant:
            self.planted["P4"] = "15:00-17:00 orders lean on chicken, burgers and stew"
        if "P5" in self.plant:
            self.planted["P5"] = f"kitchen draws {P5_EXTRA_BEEF_SHARE:.0%} more beef than sales explain, last {P5_DAYS} days"
        if "P7" in self.plant:
            self.planted["P7"] = ", ".join(sorted(d.isoformat() for d in self._p7_days)) or None
        if "P14" in self.plant:
            self.planted["P14"] = "Kasarani pays {:.0%} more for ingredients".format(cat.BRANCHES[1]["p14_cost_factor"] - 1)
        if "P6" in self.plant:
            at = local_utc(self.today - timedelta(days=2), 9, 0)
            said, counted = P6_HANDOVER
            if at <= self.now:
                db.add(models.StockTransfer(
                    restaurant_id=rid, inventory_item_id=b.inv["beef"].id, quantity=said, unit="kg", from_location="store", to_location="kitchen",
                    status=models.StockTransferStatus.DISPUTED, initiated_by_user_id=self.users["storekeeper"].id, initiated_at=at,
                    confirmed_by_user_id=self.users["kitchen"].id, confirmed_at=at + timedelta(minutes=14), confirmed_quantity=counted,
                    notes="Kitchen counted less than the store sent"))
                self._count("stock_transfers")
                self.planted["P6"] = f"store {said} kg, kitchen {counted} kg of beef on {eat_date(at).isoformat()}"
            else:
                self.planted["P6"] = None
        if "P13" in self.plant:
            db.flush()
            po = (db.query(models.PurchaseOrder).join(models.Supplier, models.Supplier.id == models.PurchaseOrder.supplier_id)
                  .join(models.InventoryItem, models.InventoryItem.id == models.PurchaseOrder.inventory_item_id)
                  .filter(models.PurchaseOrder.restaurant_id == rid, models.Supplier.name == "Kenchic", models.InventoryItem.item_name == "Chicken",
                          models.PurchaseOrder.delivered_at.isnot(None), models.PurchaseOrder.delivered_at <= self.now,
                          models.PurchaseOrder.delivered_at >= self.now - timedelta(days=25))
                  .order_by(models.PurchaseOrder.delivered_at.desc()).first())
            if po is None:
                self.planted["P13"] = None
            else:
                short = round(po.quantity_ordered * P13_RATIO, 1)
                gap = po.quantity_received - short
                po.quantity_received, po.status = short, "PARTIAL"
                po.total_cost = round(short * po.cost_per_unit)
                movement = db.query(models.StockMovement).filter(models.StockMovement.inventory_item_id == po.inventory_item_id,
                                                                  models.StockMovement.created_at == po.delivered_at,
                                                                  models.StockMovement.movement_type == models.StockMovementType.IN).first()
                if movement is not None:
                    movement.quantity = short
                inv = db.get(models.InventoryItem, po.inventory_item_id)
                inv.quantity = round(inv.quantity - gap, 4)
                self.planted["P13"] = f"Kenchic delivered {short} of {po.quantity_ordered} kg of chicken on {eat_date(po.delivered_at).isoformat()}"
        if "P15" in self.plant:
            sup = models.Supplier(restaurant_id=rid, name=P15_SUPPLIER, avg_lead_days=1.0, reliability_score=100.0, notes="Illustrative demo supplier")
            db.add(sup)
            db.flush()
            ordered = local_utc(self.today - timedelta(days=20), 17, 0)
            db.add(models.PurchaseOrder(restaurant_id=rid, supplier_id=sup.id, inventory_item_id=None, quantity_ordered=10, quantity_received=10,
                                        unit="bag", cost_per_unit=150_000, total_cost=1_500_000, status="DELIVERED", ordered_at=ordered,
                                        expected_at=ordered + timedelta(days=1), delivered_at=ordered + timedelta(days=1, minutes=20),
                                        notes="Charcoal, 10 bags"))
            self._count("suppliers")
            self._count("purchase_orders")
            self.planted["P15"] = f"{P15_SUPPLIER}: one delivery"

    # ── stock: deliveries, reorders, handovers, counts ───────────────────────
    def _deliveries(self, b: BranchState, day: date) -> None:
        """Purchase orders whose delivery falls on `day` arrive before opening: stock goes up, one IN movement each."""
        due = [po for po in b.open_pos if po.delivered_at is not None and eat_date(po.delivered_at) <= day and po.delivered_at <= self.now]
        for po in sorted(due, key=lambda p: p.delivered_at):
            inv = self.db.get(models.InventoryItem, po.inventory_item_id)
            inv.quantity = round(inv.quantity + po.quantity_received, 4)
            self.db.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.IN, quantity=po.quantity_received,
                                             reason="purchase", created_at=po.delivered_at, performed_by_user_id=self.users["storekeeper"].id))
            b.open_pos.remove(po)
            self._count("stock_movements")

    def _reorder(self, b: BranchState, day: date) -> None:
        """At closing, anything under its reorder point is ordered up to its full-shelf (par) level."""
        rng = self.rng(b.spec["key"], day.isoformat(), "po")
        open_for = {po.inventory_item_id for po in b.open_pos}
        ordered_at = local_utc(day, 21, 0)
        if ordered_at > self.now:
            return
        for ing in cat.INGREDIENTS:
            inv = b.inv[ing.key]
            reorder, par = b.reorder[ing.key]
            if inv.quantity > reorder or inv.id in open_for:
                continue
            need = par - inv.quantity
            qty = math.ceil(need / ing.pack) * ing.pack
            sup_spec = cat.SUPPLIERS[ing.supplier]
            lead = int(sup_spec["lead_days"])
            expected = local_utc(day + timedelta(days=lead), 7, 30)
            roll = rng.random()
            if roll < sup_spec["on_time"]:
                status, delivered = "DELIVERED", expected + timedelta(minutes=rng.randint(0, 40))
            else:
                status, delivered = "LATE", expected + timedelta(hours=rng.randint(20, 30))
            drift = 1.0 + 0.02 * math.sin((day - self.first_day).days / 19.0 + b.index)
            unit_cost = round(inv.cost_per_unit_cents * drift)
            po = models.PurchaseOrder(restaurant_id=b.restaurant.id, supplier_id=b.suppliers[ing.supplier].id, inventory_item_id=inv.id,
                                      quantity_ordered=qty, quantity_received=qty, unit=ing.unit, cost_per_unit=unit_cost,
                                      total_cost=round(qty * unit_cost), status=status, ordered_at=ordered_at, expected_at=expected,
                                      delivered_at=delivered, notes="")
            if delivered > self.now:
                po.status, po.delivered_at, po.quantity_received = "SENT", None, None
                b.open_pos.append(po)
                self.db.add(po)
                self._count("purchase_orders")
                continue
            self.db.add(po)
            self.db.flush()
            b.open_pos.append(po)       # arrives (and is removed) when its day comes round
            self._count("purchase_orders")

    def _handovers(self, b: BranchState, day: date) -> None:
        rng = self.rng(b.spec["key"], day.isoformat(), "handover")
        at = local_utc(day, 7, 30)
        if at > self.now:
            return
        usage_scale = WEEKLY_ORDERS * b.spec["scale"] * cat.WEEKDAY_FACTORS[day.weekday()] / 7
        per_order = cat.BASKET_MEAN_LINES * cat.LINE_MEAN_QTY
        total_w = sum(d.weight for d in cat.MENU)
        for key in PROTEINS_HANDED_OVER:
            daily = usage_scale * per_order * sum(d.weight * d.recipe.get(key, 0) for d in cat.MENU) / total_w
            qty = max(1.0, round(daily * rng.uniform(1.0, 1.15) * 2) / 2)
            self.db.add(models.StockTransfer(restaurant_id=b.restaurant.id, inventory_item_id=b.inv[key].id, quantity=qty, unit=b.inv[key].unit,
                                             from_location="store", to_location="kitchen", status=models.StockTransferStatus.CONFIRMED,
                                             initiated_by_user_id=self.users["storekeeper"].id, initiated_at=at,
                                             confirmed_by_user_id=self.users["kitchen"].id, confirmed_at=at + timedelta(minutes=12),
                                             confirmed_quantity=qty, notes=""))
            self._count("stock_transfers")

    def _weekly_close(self, b: BranchState, day: date) -> None:
        """Sunday night: the week's spoilage is written off, then the storekeeper counts the shelves."""
        at = local_utc(day, 23, 0)
        if at > self.now:
            return
        rng = self.rng(b.spec["key"], day.isoformat(), "close")
        for ing in cat.INGREDIENTS:
            inv = b.inv[ing.key]
            used = b.week_usage[ing.key]
            b.week_usage[ing.key] = 0.0
            if ing.spoils and used > 0:
                waste = round(used * b.spec["waste"] * rng.uniform(0.5, 1.5), 3)
                if waste > 0 and inv.quantity > waste:
                    inv.quantity = round(inv.quantity - waste, 4)
                    self.db.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.OUT, quantity=waste,
                                                     reason="waste", created_at=at - timedelta(minutes=30),
                                                     performed_by_user_id=self.users["storekeeper"].id))
                    self._count("stock_movements")
            book = inv.quantity
            counted = book * (1 + rng.gauss(0, 0.004))
            counted = round(counted, 1) if ing.key == "whisky" else float(round(counted)) if ing.unit in ("piece", "bottle") else round(counted, 2)
            self.db.add(models.StockCount(restaurant_id=b.restaurant.id, inventory_item_id=inv.id, expected_quantity=round(book, 3),
                                          counted_quantity=counted, counted_by_user_id=self.users["storekeeper"].id, counted_at=at,
                                          notes="Spirit counted in tenths of a bottle" if ing.key == "whisky" else ""))
            self._count("stock_counts")
            if counted != round(book, 3):
                self.db.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.ADJUST,
                                                 quantity=round(counted - book, 3), reason="stock count", created_at=at + timedelta(minutes=5),
                                                 performed_by_user_id=self.users["storekeeper"].id))
                inv.quantity = counted
                self._count("stock_movements")

    # ── people and money ─────────────────────────────────────────────────────
    def _shifts(self, b: BranchState, day: date) -> None:
        rng = self.rng(b.spec["key"], day.isoformat(), "shifts")
        for member, rate, i in b.staff:
            if day.weekday() in OFF_DAYS[i]:
                continue
            start = local_utc(day, SHIFT_STARTS[i], 0)
            if start > self.now:
                continue
            extra = 2.5 if (day.weekday() in (4, 5) and i in (1, 2) and rng.random() < 0.18) else 0.0
            hours = round(SHIFT_HOURS + extra + rng.uniform(-0.3, 0.4), 2)
            a_start = start + timedelta(minutes=rng.randint(-6, 8))
            a_end = a_start + timedelta(hours=hours)
            shift = models.LaborShift(restaurant_id=b.restaurant.id, staff_member_id=member.id, shift_date=day,
                                      scheduled_start=start, scheduled_end=start + timedelta(hours=SHIFT_HOURS), scheduled_hours=SHIFT_HOURS,
                                      actual_start=a_start, notes="")
            if a_end <= self.now:
                shift.actual_end, shift.actual_hours = a_end, hours
                shift.labor_cost = round(hours * rate)
            self.db.add(shift)
            self._count("labor_shifts")

    def _drawers(self, b: BranchState, day: date) -> None:
        """Two drawer counts a day (day shift, evening shift). Expected is the engine's own definition of what the
        register should hold; the count is usually right, sometimes a few shillings out — always inside the tolerance."""
        from ai.cash_reconciliation.intelligence import expected_cash_amount_cents
        rng = self.rng(b.spec["key"], day.isoformat(), "drawer")
        for lo, hi in ((8, 16), (16, 23)):
            ws, we = local_utc(day, lo), local_utc(day, hi)
            if we + timedelta(minutes=20) > self.now:
                continue
            expected = expected_cash_amount_cents(self.db, b.restaurant.id, ws, we)
            roll = rng.random()
            off = 0 if roll < 0.65 else -rng.randint(10, 60) * 100 if roll < 0.88 else rng.randint(10, 50) * 100
            if self.planting("P7", b) and hi == 23 and day in self._p7_days:
                off = -rng.randint(*P7_SHORT_CENTS)                  # P7: Tuesday night, short, four weeks running
            self.db.add(models.CashDrawerCount(restaurant_id=b.restaurant.id, window_start=ws, window_end=we, expected_amount_cents=expected,
                                               counted_amount_cents=max(0, expected + off), counted_by_user_id=self.users["manager"].id,
                                               counted_at=we + timedelta(minutes=15), notes=""))
            self._count("cash_drawer_counts")

    # ── bookings ─────────────────────────────────────────────────────────────
    def _reservations(self, b: BranchState, day: date, future: bool = False) -> None:
        rng = self.rng(b.spec["key"], day.isoformat(), "bookings")
        n = rng.randint(3, 6) if day.weekday() < 4 else rng.randint(7, 12)
        if future:
            n = max(1, round(n * rng.uniform(0.35, 0.8)))
        for _ in range(n):
            lunch = rng.random() < 0.3
            h, m = (rng.choice((12, 13, 14)), rng.choice((0, 30))) if lunch else (rng.choice((18, 19, 20, 21)), rng.choice((0, 15, 30, 45)))
            when = local_utc(day, h, m)
            party = rng.choices((2, 3, 4, 5, 6, 8), weights=(34, 14, 26, 10, 10, 6))[0]
            fits = [t for t in b.tables if t.capacity >= party] or b.tables
            guest = rng.choice(b.guests)
            if future:
                status = models.ReservationStatus.CANCELLED if rng.random() < 0.06 else models.ReservationStatus.CONFIRMED
            elif when > self.now:
                status = models.ReservationStatus.CONFIRMED
            else:
                r = rng.random()
                status = models.ReservationStatus.COMPLETED if r < 0.86 else models.ReservationStatus.NO_SHOW if r < 0.93 else models.ReservationStatus.CANCELLED
            self.db.add(models.Reservation(restaurant_id=b.restaurant.id, table_id=rng.choice(fits).id, customer_name=guest.name,
                                           customer_phone=guest.phone, party_size=party, reservation_date=day,
                                           reservation_time=time(h, m), duration_minutes=90, status=status,
                                           deposit_paid=party >= 6 and rng.random() < 0.4, notes="",
                                           created_at=when - timedelta(days=rng.randint(1, 6))))
            self._count("reservations")

    def _future(self, b: BranchState) -> None:
        for offset in range(1, 15):
            self._reservations(b, self.today + timedelta(days=offset), future=True)
        self._orders_on_the_way(b)

    def _orders_on_the_way(self, b: BranchState) -> None:
        """Deliveries coming up: the two items with the thinnest cover that have nothing on order get a purchase order the
        manager sent this morning, due tomorrow at 07:30 (Home's "coming up" list)."""
        on_order = {po.inventory_item_id for po in b.open_pos}
        thin = sorted((i for i in cat.INGREDIENTS if b.inv[i.key].id not in on_order),
                      key=lambda i: b.inv[i.key].quantity / max(b.reorder[i.key][1], 1e-9))[:2]
        ordered_at = min(self.now - timedelta(minutes=30), local_utc(self.today, 9, 30))
        for ing in thin:
            inv = b.inv[ing.key]
            qty = max(ing.pack, math.ceil((b.reorder[ing.key][1] - inv.quantity) / ing.pack) * ing.pack)
            self.db.add(models.PurchaseOrder(
                restaurant_id=b.restaurant.id, supplier_id=b.suppliers[ing.supplier].id, inventory_item_id=inv.id, quantity_ordered=qty,
                quantity_received=None, unit=ing.unit, cost_per_unit=inv.cost_per_unit_cents, total_cost=round(qty * inv.cost_per_unit_cents),
                status="SENT", ordered_at=ordered_at, expected_at=local_utc(self.today + timedelta(days=1), 7, 30), notes=""))
            self._count("purchase_orders")

    # ── the owner's side: approved ideas, activity, settings ─────────────────
    def _ideas_and_activity(self, owner: models.User) -> None:
        db = self.db
        for b in self.branches:
            share = b.spec["scale"]
            for name, (old, days_ago) in APPROVED_PRICE_CHANGES.items():
                dish = cat.DISH[name]
                approved_at = self.now - timedelta(days=days_ago)
                units_month = WEEKLY_ORDERS * share * cat.BASKET_MEAN_LINES * cat.LINE_MEAN_QTY * dish.weight / sum(d.weight for d in cat.MENU) * 30 / 7
                db.add(models.PricingRecommendation(
                    restaurant_id=b.restaurant.id, menu_item_id=b.menu[name].id, recommendation_type="REPRICE", current_price=old,
                    suggested_price=dish.price_cents, reason="Margin below your floor", when_to_apply="All times",
                    monthly_impact_cents=round(units_month * (dish.price_cents - old)), recommendation_strength=70, status="APPROVED",
                    created_at=approved_at - timedelta(days=2), actioned_at=approved_at))
                self._count("pricing_recommendations")
            rng = self.rng(b.spec["key"], "activity")
            agents = (("pricing_intelligence", "get_pricing_intelligence"), ("labor_intelligence", "get_labor_intelligence"),
                      ("profit_intelligence", "get_profit_intelligence"), ("inventory_predictor", "get_inventory_predictions"),
                      ("supply_chain_intelligence", "get_supply_chain_intelligence"))
            for back in range(0, 45):
                at = local_utc(self.today - timedelta(days=back), 6, 0)
                if at > self.now:
                    continue
                for agent, fn in agents:
                    db.add(models.AgentExecution(restaurant_id=b.restaurant.id, agent_name=agent, function_name=fn, success=True,
                                                 execution_ms=rng.randint(80, 400), records_processed=rng.randint(20, 90),
                                                 triggered_by="scheduler", created_at=at))
                    self._count("agent_executions")
            for back in range(0, 60):
                at = local_utc(self.today - timedelta(days=back), 7, 0)
                if at > self.now:
                    continue
                db.add(models.AgentMessage(restaurant_id=b.restaurant.id, recipient="owner", message_body="Morning briefing (demo)",
                                           message_type="morning_briefing:whatsapp", status="sent", created_at=at))
                self._count("agent_messages")
            consent_rng = self.rng(b.spec["key"], "consent")
            for g in b.guests:
                if consent_rng.random() < 0.65:
                    db.add(models.CustomerConsent(restaurant_id=b.restaurant.id, customer_phone=g.phone, purpose="marketing",
                                                  consented_at=local_utc(self.first_day, 12)))
                    self._count("customer_consents")

    def _owner_settings(self, owner: models.User) -> None:
        """The owner has chosen two targets of their own, so 'Your targets' shows a real choice (and an audit row)."""
        from owner.settings import update_settings
        for b in self.branches:
            update_settings(self.db, b.restaurant.id, owner.id, {"labour_target_pct": 32, "urgent_alerts_per_day": 3})


def build(db, owner_email: str, owner_password: str, *, seed: int = DEFAULT_SEED, now: datetime | None = None,
          days: int = DEFAULT_DAYS, plant: tuple = PLANTS) -> DemoSummary:
    return DemoBuilder(db, seed=seed, now=now, days=days, plant=plant).build(owner_email, owner_password)
