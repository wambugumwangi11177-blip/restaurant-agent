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
APPROVED_PRICE_CHANGES = {"Ugali sukuma": (25_000, 20), "Chicken wings": (55_000, 41)}   # (old price, days ago approved); the menu holds the new price


def local_utc(day: date, hour: int, minute: int = 0) -> datetime:
    """A Nairobi wall-clock time as a naive-UTC datetime (the way every DateTime column stores it)."""
    return datetime(day.year, day.month, day.day, hour, minute) - EAT_OFFSET


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

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("tenant_id", "restaurant_ids", "seed", "days", "counts", "weekly_sales_kes", "wiped")}


class DemoBuilder:
    def __init__(self, db, *, seed: int = DEFAULT_SEED, now: datetime | None = None, days: int = DEFAULT_DAYS,
                 plant: tuple = ()):
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
        self._ideas_and_activity(owner)
        self._owner_settings(owner)
        owner.active_restaurant_id = self.branches[0].restaurant.id
        db.commit()
        weekly = {b.spec["key"]: round(self.sales_cents.get(b.spec["key"], 0) / 100 / (self.days / 7), 2) for b in self.branches}
        return DemoSummary(tenant.id, [b.restaurant.id for b in self.branches], self.seed, self.now, self.days,
                           dict(sorted(self.counts.items())), weekly,
                           {b.spec["key"]: dict(b.min_stock) for b in self.branches}, wiped)

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
            cost = round(ing.cost_cents * spec["cost_factor"])
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
    def price_on(self, dish: cat.Dish, day: date) -> int:
        change = APPROVED_PRICE_CHANGES.get(dish.name)
        if change is not None and day < self.today - timedelta(days=change[1]):
            return change[0]
        return dish.price_cents

    def _plan_orders(self, b: BranchState, day: date) -> list[dict]:
        rng = self.rng(b.spec["key"], day.isoformat(), "orders")
        expected = WEEKLY_ORDERS * b.spec["scale"] * cat.WEEKDAY_FACTORS[day.weekday()] / 7
        if day.day >= 25:
            expected *= 1.06                       # payday week
        n = max(4, round(expected * rng.gauss(1.0, 0.08)))
        weights = [d.weight for d in cat.MENU]
        active = [g for g in b.guests if g.lapses_on is None or day < g.lapses_on]
        parts = cat.DAYPARTS
        plans = []
        for _ in range(n):
            name, h0, h1, _share = rng.choices(parts, weights=[p[3] for p in parts])[0]
            when = local_utc(day, rng.randrange(h0, h1), rng.randrange(0, 60))
            if when > self.now:
                continue                           # nothing in the future
            k = rng.choices(cat.BASKET_SIZES, weights=cat.BASKET_WEIGHTS)[0]
            picked: list[cat.Dish] = []
            pool, pw = list(cat.MENU), list(weights)
            for _line in range(k):
                i = rng.choices(range(len(pool)), weights=pw)[0]
                picked.append(pool.pop(i))
                pw.pop(i)
            lines = [(d, rng.choices(cat.LINE_QTYS, weights=cat.LINE_QTY_WEIGHTS)[0], self.price_on(d, day)) for d in picked]
            r = rng.random()
            channel, otype = (models.DeliveryChannel.GLOVO, models.OrderType.DELIVERY) if r < 0.13 else \
                (models.DeliveryChannel.UBER_EATS, models.OrderType.DELIVERY) if r < 0.22 else \
                (models.DeliveryChannel.BOLT_FOOD, models.OrderType.DELIVERY) if r < 0.26 else \
                (models.DeliveryChannel.APP, models.OrderType.TAKEOUT) if r < 0.29 else \
                (models.DeliveryChannel.WALK_IN, models.OrderType.DINE_IN if rng.random() < 0.75 else models.OrderType.TAKEOUT)
            if channel in (models.DeliveryChannel.GLOVO, models.DeliveryChannel.UBER_EATS, models.DeliveryChannel.BOLT_FOOD):
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
        self._count("orders", len(written))
        self._count("order_items", sum(len(o.items) for o, _p in written))
        self._count("prep_times", sum(len(o.items) for o, _p in written if o.status != models.OrderStatus.CANCELLED))

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
          days: int = DEFAULT_DAYS, plant: tuple = ()) -> DemoSummary:
    return DemoBuilder(db, seed=seed, now=now, days=days, plant=plant).build(owner_email, owner_password)
