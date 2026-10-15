"""
backend/tests/fixtures/golden_restaurant.py
────────────────────────────────────────────
A small, fully deterministic restaurant whose engine answers are the worked
examples of docs/v2/SPEC.md §7. Used by tests/evals/test_e2_money_goldens.py
(and later by the owner-API and coverage evals).

Shape: one shared SKELETON (tenant, restaurant, four staff roles, one supplier,
eight dishes with recipes and costs) plus ONE SEEDER PER WORKED EXAMPLE. The
spec's "one week" fixture cannot be literal — its own numbers cannot coexist in
a single week (400 chips sold at KES 270 is already KES 108,000, more than the
KES 100,000 of weekly sales in example #1) — so each seeder adds only the rows
its example needs, and every test gets a fresh database (the `db_session`
fixture), so scenarios never contaminate each other.

Determinism: no randomness. Everything is placed relative to `Golden.now`
(naive UTC, taken once from `time_utils.utcnow()`), because ~40 modules import
`utcnow` by value and cannot be clock-patched globally. Offsets are fixed, so
the *numbers* the engines return do not depend on when the test runs.

Money is integer cents throughout, as in models.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import auth
import models
from time_utils import utcnow

# name, category, price (cents), cost (cents)  — SPEC §6 / §7 prices where given.
MENU = [
    ("Quarter chicken", "Mains", 40_000, 26_000),   # §7 #3: cost ratio 65% → below the 40% margin floor
    ("Chips",           "Sides", 30_000,  9_000),   # §7 #5
    ("Burger",          "Mains", 60_000, 28_000),   # §7 #6
    ("Nyama choma",     "Mains", 90_000, 27_000),
    ("Fish fillet",     "Mains", 65_000, 26_000),
    ("Spaghetti",       "Mains", 45_000, 24_000),
    ("Pilau",           "Mains", 35_000, 11_000),
    ("Beef stew",       "Mains", 55_000, 20_000),   # §7 #7: 0.25 kg beef per serving
]

# name, unit, cost per unit (cents), opening quantity, reorder point, par level
INGREDIENTS = [
    ("Beef",     "kg", 80_000, 50.0, 10, 60.0),
    ("Chicken",  "kg", 45_000, 40.0, 10, 50.0),
    ("Potatoes", "kg",  9_000, 60.0, 15, 80.0),
    ("Rice",     "kg", 15_000, 40.0, 10, 50.0),
    ("Tilapia",  "kg", 60_000, 20.0,  5, 25.0),
    ("Pasta",    "kg", 20_000, 15.0,  5, 20.0),
]

# dish -> [(ingredient, quantity per serving)]
RECIPES = {
    "Quarter chicken": [("Chicken", 0.35)],
    "Chips":           [("Potatoes", 0.30)],
    "Burger":          [("Beef", 0.18)],
    "Nyama choma":     [("Beef", 0.40)],
    "Fish fillet":     [("Tilapia", 0.30)],
    "Spaghetti":       [("Pasta", 0.12)],
    "Pilau":           [("Rice", 0.15)],
    "Beef stew":       [("Beef", 0.25)],
}


@dataclass
class Golden:
    now: datetime
    tenant: models.Tenant
    restaurant: models.Restaurant
    owner: models.User
    manager: models.User
    storekeeper: models.User
    kitchen: models.User
    supplier: models.Supplier
    items: dict = field(default_factory=dict)       # dish name -> MenuItem
    inventory: dict = field(default_factory=dict)   # ingredient name -> InventoryItem

    @property
    def rid(self) -> int:
        return self.restaurant.id


def _user(db, tenant, email, role, staff_role):
    user = models.User(
        tenant_id=tenant.id, email=email, hashed_password=auth.get_password_hash("x"),
        role=role, staff_role=staff_role, token_version=0,
    )
    db.add(user)
    return user


def build_skeleton(db, *, now: datetime | None = None, suffix: str = "gold") -> Golden:
    """Tenant + restaurant + staff + supplier + 8 dishes with recipes. No orders."""
    now = (now or utcnow()).replace(microsecond=0)
    tenant = models.Tenant(name=f"Golden Tenant {suffix}")
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Golden Grill {suffix}", address="Nairobi")
    db.add(restaurant)
    owner = _user(db, tenant, f"owner-{suffix}@golden.test", models.Role.ADMIN, models.StaffRole.OWNER)
    manager = _user(db, tenant, f"manager-{suffix}@golden.test", models.Role.STAFF, models.StaffRole.MANAGER)
    storekeeper = _user(db, tenant, f"store-{suffix}@golden.test", models.Role.STAFF, models.StaffRole.STOCKKEEPER)
    kitchen = _user(db, tenant, f"kitchen-{suffix}@golden.test", models.Role.STAFF, models.StaffRole.KITCHEN)
    db.flush()
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Golden Meats", reliability_score=100.0)
    db.add(supplier)
    db.flush()

    g = Golden(now=now, tenant=tenant, restaurant=restaurant, owner=owner, manager=manager,
               storekeeper=storekeeper, kitchen=kitchen, supplier=supplier)

    for name, category, price, cost in MENU:
        item = models.MenuItem(restaurant_id=restaurant.id, name=name, category=category,
                               price=price, cost_price=cost, is_available=True)
        db.add(item)
        g.items[name] = item
    for name, unit, cost_cents, qty, reorder, par in INGREDIENTS:
        inv = models.InventoryItem(
            restaurant_id=restaurant.id, item_name=name, unit=unit, quantity=qty,
            cost_per_unit_cents=cost_cents, low_stock_threshold=reorder, par_level=par,
            default_supplier_id=supplier.id,
        )
        db.add(inv)
        g.inventory[name] = inv
    db.flush()
    for dish, parts in RECIPES.items():
        for ingredient, per_serving in parts:
            db.add(models.MenuIngredient(
                menu_item_id=g.items[dish].id, inventory_item_id=g.inventory[ingredient].id,
                quantity_per_serving=per_serving,
            ))
    db.commit()
    return g


def add_order(db, g: Golden, lines, at: datetime, *,
              channel=models.DeliveryChannel.WALK_IN, payment=models.PaymentMethod.CASH,
              paid: bool = True, status=models.OrderStatus.SERVED,
              order_type=models.OrderType.DINE_IN) -> models.Order:
    """One order. `lines` = [(MenuItem, quantity, unit_price_cents)]. Not committed."""
    order = models.Order(
        restaurant_id=g.rid, status=status, order_type=order_type, delivery_channel=channel,
        payment_method=payment, is_paid=paid, created_at=at, completed_at=at,
        total=sum(qty * unit for _item, qty, unit in lines),
    )
    for item, qty, unit in lines:
        order.items.append(models.OrderItem(menu_item_id=item.id, quantity=qty, unit_price=unit))
    db.add(order)
    return order


# ─── one seeder per worked example ───────────────────────────────────────────

def seed_chicken_reprice(db, g: Golden) -> None:
    """§7 #3 — 300 Quarter chickens sold in the 30 days before `now`, at the menu price.

    30 on the most recent day and 10 a day for the 27 days before it: total 300, and the
    newest 30 orders sit within ~3.5 hours of `now`, so `analysis_anchor` (the 30th most
    recent order) leaves the whole 30-day window covering all 300.
    """
    chicken = g.items["Quarter chicken"]
    plan = [(0, 30)] + [(day, 10) for day in range(1, 28)]
    for days_ago, count in plan:
        for k in range(count):
            add_order(db, g, [(chicken, 1, chicken.price)], g.now - timedelta(days=days_ago, minutes=7 * k))
    db.commit()


def seed_chips_below_menu(db, g: Golden) -> None:
    """§7 #5 — 400 chips lines in the last 14 days, each charged KES 270 against a KES 300 menu price."""
    chips = g.items["Chips"]
    for i in range(400):
        add_order(db, g, [(chips, 1, 27_000)], g.now - timedelta(minutes=46 * i))
    db.commit()


def seed_burger_delivery(db, g: Golden) -> None:
    """§7 #6 — the same KES 600 burger: 6 plates on Glovo (25% commission) and 6 dine-in."""
    burger = g.items["Burger"]
    for i in range(6):
        add_order(db, g, [(burger, 1, burger.price)], g.now - timedelta(minutes=90 * i),
                  channel=models.DeliveryChannel.GLOVO, payment=models.PaymentMethod.CARD,
                  order_type=models.OrderType.DELIVERY)
    for i in range(6):
        add_order(db, g, [(burger, 1, burger.price)], g.now - timedelta(minutes=90 * i + 45))
    db.commit()


def seed_beef_variance(db, g: Golden) -> None:
    """§7 #7 — beef: opening 50 kg, delivered 30, closing 40 → 40 kg used; 120 stews × 0.25 kg = 30 kg expected."""
    beef, stew = g.inventory["Beef"], g.items["Beef stew"]
    for i in range(120):
        add_order(db, g, [(stew, 1, stew.price)], g.now - timedelta(minutes=30 * i))
    db.add(models.PurchaseOrder(
        restaurant_id=g.rid, supplier_id=g.supplier.id, inventory_item_id=beef.id,
        quantity_ordered=30.0, quantity_received=30.0, unit="kg", cost_per_unit=80_000,
        total_cost=2_400_000, status="DELIVERED", ordered_at=g.now - timedelta(days=4),
        expected_at=g.now - timedelta(days=3), delivered_at=g.now - timedelta(days=3),
    ))
    db.add(models.StockMovement(
        inventory_item_id=beef.id, movement_type=models.StockMovementType.IN, quantity=30.0,
        reason="purchase", created_at=g.now - timedelta(days=3), performed_by_user_id=g.storekeeper.id,
    ))
    for k in range(4):
        db.add(models.StockMovement(
            inventory_item_id=beef.id, movement_type=models.StockMovementType.OUT, quantity=10.0,
            reason="issued to kitchen", created_at=g.now - timedelta(days=k, hours=1),
            performed_by_user_id=g.kitchen.id,
        ))
    beef.quantity = 40.0   # 50 + 30 − 40
    db.commit()


def seed_handover(db, g: Golden) -> models.StockTransfer:
    """Store→kitchen: the store declares 40 kg of beef, the kitchen will count 38 (SPEC fig 6.1 P6)."""
    transfer = models.StockTransfer(
        restaurant_id=g.rid, inventory_item_id=g.inventory["Beef"].id, quantity=40.0, unit="kg",
        from_location="store", to_location="kitchen", status=models.StockTransferStatus.PENDING,
        initiated_by_user_id=g.storekeeper.id, initiated_at=g.now - timedelta(hours=2),
    )
    db.add(transfer)
    db.commit()
    return transfer


def seed_cash_orders(db, g: Golden, *, start: datetime, count: int, each_cents: int = 50_000) -> int:
    """`count` paid cash orders inside a drawer window. Returns the expected drawer total in cents."""
    pilau = g.items["Pilau"]
    for k in range(count):
        add_order(db, g, [(pilau, 1, each_cents)], start + timedelta(minutes=6 * k))
    db.commit()
    return count * each_cents


def seed_cash_drawers(db, g: Golden):
    """§7 #8 — two shifts. A: KES 35,000 expected, counted KES 520 short. B: KES 20,000 expected, KES 150 short.

    Returns [(window_start, window_end, expected_cents, counted_cents), ...]; the test records the
    counts through the real `record_drawer_count` so the engine, not the fixture, does the maths.
    """
    a_start, b_start = g.now - timedelta(hours=30), g.now - timedelta(hours=20)
    a_expected = seed_cash_orders(db, g, start=a_start, count=70)
    b_expected = seed_cash_orders(db, g, start=b_start, count=40)
    return [
        (a_start, a_start + timedelta(hours=8), a_expected, a_expected - 52_000),
        (b_start, b_start + timedelta(hours=8), b_expected, b_expected - 15_000),
    ]


def seed_pnl_week(db, g: Golden, *, price_rise: bool = False) -> models.MenuItem:
    """§7 #1/#2 — a week of KES 100,000 sales, KES 32,000 ingredients, KES 25,000 wages.

    One dedicated "House set meal" (KES 1,000, cost KES 320) is sold 100 times so the totals are exact
    by construction. `price_rise=True` re-prices the same 100 plates +5% → KES 105,000 (example #2).
    Wages: 25 shifts × 8 h × KES 125/h = KES 25,000.
    """
    meal = models.MenuItem(restaurant_id=g.rid, name="House set meal", category="Mains",
                           price=100_000, cost_price=32_000, is_available=True)
    db.add(meal)
    db.flush()
    unit = 105_000 if price_rise else 100_000
    per_day = [15, 15, 14, 14, 14, 14, 14]            # 100 orders over 7 days
    for day, count in enumerate(per_day):
        for k in range(count):
            add_order(db, g, [(meal, 1, unit)], g.now - timedelta(days=day, minutes=10 * k))
    staff = []
    for n in range(5):
        member = models.StaffMember(restaurant_id=g.rid, name=f"Staff {n + 1}", role_title="Waiter",
                                    hourly_rate=12_500)
        db.add(member)
        staff.append(member)
    db.flush()
    for member in staff:
        for day in range(5):
            shift_day = g.now - timedelta(days=day)
            db.add(models.LaborShift(
                restaurant_id=g.rid, staff_member_id=member.id, shift_date=shift_day.date(),
                scheduled_hours=8.0, actual_hours=8.0, labor_cost=100_000,
                actual_start=shift_day.replace(hour=6), actual_end=shift_day.replace(hour=14),
            ))
    db.commit()
    return meal


# ─── seeders for the settings-driven behaviour tests (S1.2) ──────────────────

def pin_anchor(db, g: Golden, n: int = 30) -> None:
    """Make the analysis anchor ≈ `now`: the 30th most recent order sits within the last hour.

    `ai.analysis_clock.analysis_anchor` is the date of the 30th most recent order, so a scenario that
    wants its windows aligned to `now` needs 30 recent orders. These are cheap Spaghetti orders (margin
    46.7%, one day of history) — no pricing recommendation and no velocity signal of their own.
    """
    spaghetti = g.items["Spaghetti"]
    for k in range(n):
        add_order(db, g, [(spaghetti, 1, spaghetti.price)], g.now - timedelta(minutes=2 * k))
    db.commit()


def seed_chips_surge(db, g: Golden) -> None:
    """Chips (margin 70%) that suddenly sell hot: 1/day for days 7–29, then 5/day for the last 7 days."""
    chips = g.items["Chips"]
    for day in range(7, 30):
        add_order(db, g, [(chips, 1, chips.price)], g.now - timedelta(days=day, hours=1))
    for day in range(0, 7):
        for k in range(5):
            add_order(db, g, [(chips, 1, chips.price)], g.now - timedelta(days=day, hours=2 + k))
    db.commit()
    pin_anchor(db, g)


def seed_slow_pilau(db, g: Golden) -> None:
    """Pilau (margin 68.6%) that went quiet: 5/day for days 7–29, one plate in the last week."""
    pilau = g.items["Pilau"]
    for day in range(7, 30):
        for k in range(5):
            add_order(db, g, [(pilau, 1, pilau.price)], g.now - timedelta(days=day, hours=1 + k))
    add_order(db, g, [(pilau, 1, pilau.price)], g.now - timedelta(days=3))
    db.commit()
    pin_anchor(db, g)


def seed_menu_mix(db, g: Golden) -> None:
    """Units sold over the last 20 days chosen so the popular cut-off (0.7 × the average) matters.

    Eight dishes, 400 units: average 50 units/dish → cut-off 35 at 0.7 and 50 at 1.0. Dishes selling 40
    units are popular at 0.7 and not at 1.0.
    """
    plan = {"Quarter chicken": 100, "Chips": 90, "Burger": 40, "Nyama choma": 40, "Fish fillet": 40,
            "Spaghetti": 30, "Pilau": 40, "Beef stew": 20}
    k = 0
    for name, units in plan.items():
        item = g.items[name]
        for i in range(units):
            add_order(db, g, [(item, 1, item.price)], g.now - timedelta(hours=1 + (k % 400)))
            k += 1
    db.commit()


def seed_overtime_shift(db, g: Golden, hours: float = 8.5) -> None:
    """One 8.5-hour shift (KES 125/h) and some sales, so labour % and overtime have something to read."""
    pilau = g.items["Pilau"]
    for k in range(40):
        add_order(db, g, [(pilau, 1, pilau.price)], g.now - timedelta(minutes=20 * k))
    member = models.StaffMember(restaurant_id=g.rid, name="Closer", role_title="Waiter", hourly_rate=12_500)
    db.add(member)
    db.flush()
    db.add(models.LaborShift(
        restaurant_id=g.rid, staff_member_id=member.id, shift_date=g.now.date(),
        scheduled_hours=8.0, actual_hours=hours, labor_cost=int(hours * 12_500),
        actual_start=g.now.replace(hour=6), actual_end=g.now.replace(hour=14, minute=30)))
    db.commit()
