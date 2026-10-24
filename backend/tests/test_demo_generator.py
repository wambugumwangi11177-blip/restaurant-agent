"""
S2.1 — the deterministic demo generator (docs/v2/SPEC.md §6).

What this pins:
  * the catalog: the dishes figure 6.1 fixes (Quarter chicken 400/260, Chips 300/90, Burger 600/280, Fish 650/260,
    Pilau 350) fall out of the recipes; the menu sorts into Star · Puzzle · Plowhorse · Dog the way P11 needs;
  * the shape: one tenant, two branches, 120 days, ~28 dishes with recipes whose cost is the sum of their ingredients,
    about KES 100,000 a week per branch, tables, bookings (past and next 14 days), shifts, suppliers, purchase orders and
    deliveries, weekly stock counts, store→kitchen handovers, two drawer counts a day, kitchen prep times;
  * honesty: nothing in the future, no negative stock, no payment reference, no dialable phone number, no login anyone
    knows the password of;
  * determinism and idempotency: the same seed gives the same rows, re-seeding twice gives the same rows and no duplicates,
    a different seed gives different rows; weekday patterns follow the calendar;
  * safety: only the "Demo Restaurant" tenant can be wiped, other tenants' rows are untouched, every table that hangs off a
    restaurant is either wiped or explicitly kept, and the CLI refuses any database that is not on this machine;
  * the point of it all: every built engine in the registry has real output on the demo.
"""
import hashlib
import importlib.util
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func

import models
from demo import catalog as cat
from demo import safety
from demo.generator import DEFAULT_DAYS, build
from demo.wipe import KEPT, KEPT_CHILDREN, WIPED, WipeRefused, wipe_demo
from time_utils import eat_date, utcnow

OWNER, PASSWORD = "owner@demo-restaurant.example", "Demo-Passw0rd!x"
NOW = datetime(2026, 10, 14, 13, 30)            # Wednesday 16:30 in Nairobi
ROOT = Path(__file__).resolve().parents[2]


def _scratch_session(tmp_path_factory, name):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp(name) / 'demo.db'}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """One demo build (fixed clock) shared by the read-only tests: building takes seconds, asserting takes none."""
    engine, db = _scratch_session(tmp_path_factory, "shared")
    summary = build(db, OWNER, PASSWORD, now=NOW, plant=())            # the baseline: no scenario planted
    yield db, summary
    db.close()
    engine.dispose()


@pytest.fixture
def fresh_demo(db_session):
    return db_session, build(db_session, OWNER, PASSWORD, now=NOW)


def _branches(db):
    return db.query(models.Restaurant).join(models.Tenant).filter(models.Tenant.name == "Demo Restaurant").order_by(models.Restaurant.id).all()


def fingerprint(db) -> str:
    """A hash of the demo's business rows with every database id left out (ids differ between runs; content must not)."""
    h = hashlib.sha256()

    def feed(rows):
        for text in sorted(repr(row) for row in rows):
            h.update(text.encode())

    names = {m.id: m.name for m in db.query(models.MenuItem).all()}
    inv = {i.id: i.item_name for i in db.query(models.InventoryItem).all()}
    rest = {r.id: r.name for r in _branches(db)}
    feed((rest[o.restaurant_id], o.created_at, o.status.value, o.order_type.value, o.delivery_channel.value, o.payment_method.value,
                 o.is_paid, o.total, o.customer_phone, o.table_number,
                 tuple(sorted((names[i.menu_item_id], i.quantity, i.unit_price, i.prep_time.actual_minutes if i.prep_time else None) for i in o.items)))
                for o in db.query(models.Order).filter(models.Order.restaurant_id.in_(list(rest))).all())
    feed((rest[m.restaurant_id], m.name, m.price, m.cost_price) for m in db.query(models.MenuItem).all())
    feed((inv[m.inventory_item_id], m.movement_type.value, m.quantity, m.created_at, m.reason.split("#")[0]) for m in db.query(models.StockMovement).all())
    feed((rest[p.restaurant_id], inv.get(p.inventory_item_id), p.quantity_ordered, p.status, p.ordered_at, p.delivered_at) for p in db.query(models.PurchaseOrder).all())
    feed((rest[s.restaurant_id], s.shift_date, s.staff_member_id and s.actual_hours, s.labor_cost) for s in db.query(models.LaborShift).all())
    feed((rest[c.restaurant_id], c.window_start, c.expected_amount_cents, c.counted_amount_cents) for c in db.query(models.CashDrawerCount).all())
    feed((rest[r.restaurant_id], r.reservation_date, r.reservation_time, r.party_size, r.status.value) for r in db.query(models.Reservation).all())
    feed((inv[c.inventory_item_id], c.counted_at, c.counted_quantity) for c in db.query(models.StockCount).all())
    feed((inv[t.inventory_item_id], t.initiated_at, t.quantity, t.confirmed_quantity) for t in db.query(models.StockTransfer).all())
    return h.hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# The catalog
# ═════════════════════════════════════════════════════════════════════════════

def test_the_dishes_figure_6_1_fixes_come_out_of_the_recipes():
    fixed = {"Quarter chicken": (40_000, 26_000), "Chips": (30_000, 9_000), "Burger": (60_000, 28_000),
             "Fish fillet": (65_000, 26_000), "Pilau": (35_000, None)}
    for name, (price, cost) in fixed.items():
        dish = cat.DISH[name]
        assert dish.price_cents == price, name
        if cost is not None:
            assert dish.cost_cents == cost, name
    assert 26 <= len(cat.MENU) <= 32
    names = {d.name for d in cat.MENU}
    for required in ("Quarter chicken", "Chips", "Burger", "Fish fillet", "Pilau", "Beef stew", "Fried rice", "Chai (milk tea)", "Soda", "Beer", "Whisky (shot)"):
        assert required in names
    assert sum(1 for n in names if "juice" in n.lower()) >= 3 and any("Nyama choma" in n for n in names) and any("Spaghetti" in n for n in names)


def test_every_recipe_uses_known_ingredients_and_every_ingredient_is_used():
    used = set()
    for dish in cat.MENU:
        assert dish.recipe, dish.name
        assert set(dish.recipe) <= set(cat.ING), dish.name
        used |= set(dish.recipe)
    assert used == set(cat.ING), f"unused ingredients: {set(cat.ING) - used}"
    assert {i.supplier for i in cat.INGREDIENTS} <= set(cat.SUPPLIERS)


def test_the_menu_sorts_into_star_puzzle_plowhorse_and_dog_as_p11_needs():
    """The menu engine's own rule: popular = sells at least 70% of the mean; profitable = unit margin at least the mean margin."""
    mean_w = sum(d.weight for d in cat.MENU) / len(cat.MENU)
    mean_margin = sum(d.price_cents - d.cost_cents for d in cat.MENU) / len(cat.MENU)

    def quadrant(d):
        popular, profitable = d.weight >= 0.7 * mean_w, d.price_cents - d.cost_cents >= mean_margin
        return "Star" if popular and profitable else "Plowhorse" if popular else "Puzzle" if profitable else "Dog"
    assert quadrant(cat.DISH["Nyama choma (goat)"]) == "Star"
    assert quadrant(cat.DISH["Fish fillet"]) == "Puzzle"
    assert quadrant(cat.DISH["Chips"]) == "Plowhorse"
    assert quadrant(cat.DISH["Spaghetti bolognese"]) == "Dog"


def test_the_weekly_target_is_a_hundred_thousand_shillings_per_branch():
    assert cat.WEEKLY_SALES_TARGET_CENTS == 10_000_000
    assert abs(sum(cat.WEEKDAY_FACTORS) / 7 - 1.0) < 1e-9
    assert 0.28 <= sum(d.cost_cents * d.weight for d in cat.MENU) / sum(d.price_cents * d.weight for d in cat.MENU) <= 0.34


def test_no_real_person_or_business_is_named_except_the_one_figure_6_1_names():
    assert [s["name"] for s in cat.SUPPLIERS.values() if s["name"] == "Kenchic"]        # P13 names Kenchic
    assert all(len(n) < 12 for n in cat.GUEST_NAMES)


# ═════════════════════════════════════════════════════════════════════════════
# The shape of the demo
# ═════════════════════════════════════════════════════════════════════════════

def test_demo_seed_has_store_kitchen_manager_and_accountant_logins(demo):
    db, _summary = demo
    expected = {
        "manager@demo-restaurant.example": models.StaffRole.MANAGER,
        "store@demo-restaurant.example": models.StaffRole.STOCKKEEPER,
        "kitchen@demo-restaurant.example": models.StaffRole.KITCHEN,
        "accountant@demo-restaurant.example": models.StaffRole.CONTROLLER,
    }
    branches = _branches(db)
    for email, role in expected.items():
        user = db.query(models.User).filter_by(email=email).one()
        assert user.staff_role == role and user.is_active and user.role == models.Role.STAFF
        assert user.active_restaurant_id == branches[0].id
        roster = db.query(models.StaffMember).filter_by(user_id=user.id).all()
        assert len(roster) == 1 and roster[0].restaurant_id == branches[0].id


def test_one_tenant_two_branches_with_the_owner_login_resolving_the_first(demo):
    db, summary = demo
    tenant = db.query(models.Tenant).filter(models.Tenant.name == "Demo Restaurant").one()
    branches = _branches(db)
    assert [b.name for b in branches] == ["Demo Restaurant", "Demo Restaurant – Kasarani"]
    assert [b.address for b in branches] == ["Westlands, Nairobi", "Kasarani, Nairobi"]
    assert {b.tenant_id for b in branches} == {tenant.id}
    assert len({b.organization_id for b in branches}) == 1 and branches[0].organization_id is not None
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    assert owner.staff_role == models.StaffRole.OWNER and owner.active_restaurant_id == branches[0].id
    assert summary.restaurant_ids == [b.id for b in branches]


def test_each_branch_has_a_full_menu_with_recipes_and_honest_costs(demo):
    db, _ = demo
    for r in _branches(db):
        items = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == r.id).all()
        assert len(items) == len(cat.MENU)
        inv = {i.id: i for i in db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == r.id)}
        assert len(inv) == len(cat.INGREDIENTS)
        for item in items:
            recipe = db.query(models.MenuIngredient).filter(models.MenuIngredient.menu_item_id == item.id).all()
            assert recipe, f"{item.name} has no recipe"
            assert {m.inventory_item_id for m in recipe} <= set(inv)                          # recipes never cross branches
            assert item.cost_price == round(sum(m.raw_quantity_per_serving * inv[m.inventory_item_id].cost_per_unit_cents for m in recipe)), item.name
        chicken = next(i for i in items if i.name == "Quarter chicken")
        assert (chicken.price, chicken.cost_price) == (40_000, 26_000)


def test_about_a_hundred_thousand_shillings_a_week_per_branch(demo):
    db, summary = demo
    for r in _branches(db):
        end = NOW
        rows = db.query(func.sum(models.Order.total)).filter(
            models.Order.restaurant_id == r.id, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= end - timedelta(days=56), models.Order.created_at < end).scalar()
        weekly = rows / 100 / 8
        assert 85_000 <= weekly <= 115_000, (r.name, weekly)
    assert all(85_000 <= v <= 115_000 for v in summary.weekly_sales_kes.values())


def test_a_hundred_and_twenty_days_with_nothing_in_the_future(demo):
    db, _ = demo
    rids = [r.id for r in _branches(db)]
    first, last = db.query(func.min(models.Order.created_at), func.max(models.Order.created_at)).filter(models.Order.restaurant_id.in_(rids)).one()
    assert (eat_date(NOW) - eat_date(first)).days >= DEFAULT_DAYS - 2
    assert last <= NOW
    assert db.query(models.LaborShift).filter(models.LaborShift.actual_end > NOW).count() == 0
    assert db.query(models.CashDrawerCount).filter(models.CashDrawerCount.window_end > NOW).count() == 0
    assert db.query(models.StockMovement).filter(models.StockMovement.created_at > NOW).count() == 0
    assert db.query(models.PurchaseOrder).filter(models.PurchaseOrder.delivered_at > NOW).count() == 0
    assert db.query(models.StockTransfer).filter(models.StockTransfer.initiated_at > NOW).count() == 0
    assert db.query(models.StockCount).filter(models.StockCount.counted_at > NOW).count() == 0
    past = db.query(models.Reservation).filter(models.Reservation.reservation_date <= eat_date(NOW)).count()
    future = db.query(models.Reservation).filter(models.Reservation.reservation_date > eat_date(NOW)).count()
    assert past > 500 and future >= 20
    assert db.query(models.Reservation).filter(models.Reservation.reservation_date > eat_date(NOW), models.Reservation.status == models.ReservationStatus.COMPLETED).count() == 0


def test_every_part_of_the_restaurant_is_there(demo):
    db, summary = demo
    c = summary.counts
    for key, minimum in {"orders": 3000, "order_items": 6000, "prep_times": 6000, "stock_movements": 15000, "purchase_orders": 150,
                         "stock_counts": 800, "stock_transfers": 1000, "cash_drawer_counts": 400, "labor_shifts": 1000, "reservations": 1000,
                         "suppliers": 14, "staff_members": 14, "tables": 24, "customer_feedback": 100, "customer_consents": 100,
                         "pricing_recommendations": 3, "agent_executions": 100}.items():
        assert c[key] >= minimum, (key, c[key])
    kinds = Counter(m.movement_type for m in db.query(models.StockMovement).all())
    assert set(kinds) == {models.StockMovementType.IN, models.StockMovementType.OUT, models.StockMovementType.ADJUST}
    assert db.query(models.PurchaseOrder).filter(models.PurchaseOrder.status == "LATE").count() > 0           # some trucks are late
    assert db.query(models.PurchaseOrder).filter(models.PurchaseOrder.status == "SENT").count() > 0           # and some are on the way
    status = Counter(o.status for o in db.query(models.Order).all())
    assert status[models.OrderStatus.SERVED] > 3000 and status[models.OrderStatus.CANCELLED] > 20
    assert {o.delivery_channel for o in db.query(models.Order).all()} == set(models.DeliveryChannel)
    assert db.query(models.StockCount).filter(models.StockCount.counted_quantity != models.StockCount.expected_quantity).count() > 0


def test_two_drawer_counts_a_day_and_all_of_them_inside_the_tolerance(demo):
    db, _ = demo
    from owner.settings import DEFAULTS
    per_day = Counter((c.restaurant_id, eat_date(c.window_start)) for c in db.query(models.CashDrawerCount).all())
    assert set(per_day.values()) == {2} or set(per_day.values()) <= {1, 2}
    assert sum(1 for v in per_day.values() if v == 2) >= 2 * (DEFAULT_DAYS - 3)
    worst = max(abs(c.counted_amount_cents - c.expected_amount_cents) for c in db.query(models.CashDrawerCount).all())
    assert worst < DEFAULTS.cash_tolerance_cents                       # the baseline is clean; P7 plants the Tuesday shortage


def test_stock_is_never_negative_and_matches_the_books(demo):
    db, summary = demo
    for branch, lows in summary.min_stock.items():
        assert min(lows.values()) >= 0, (branch, {k: v for k, v in lows.items() if v < 0})
    for inv in db.query(models.InventoryItem).all():
        assert inv.quantity >= 0
        assert inv.par_level and inv.low_stock_threshold and inv.default_supplier_id
        assert inv.low_stock_threshold < inv.par_level


def test_baseline_waste_is_inside_the_missing_stock_line(demo, monkeypatch):
    """The baseline kitchen wastes a little; nothing is flagged as missing stock until P5 plants it."""
    from ai.stock_custody import compute_variance_report
    db, _ = demo
    import ai.stock_custody as sc
    monkeypatch.setattr(sc, "utcnow", lambda: NOW)
    for r in _branches(db):
        rows = compute_variance_report(db, r.id, hours=24 * 7)
        assert rows
        assert not [row for row in rows if row.flagged and row.variance_pct is not None and row.variance_pct > 0.2]


def test_staff_are_paid_for_the_hours_they_work(demo):
    db, _ = demo
    done = db.query(models.LaborShift).filter(models.LaborShift.actual_end.isnot(None)).all()
    assert done
    rates = {m.id: m.hourly_rate for m in db.query(models.StaffMember).all()}
    for s in done[:300]:
        assert s.labor_cost == round(s.actual_hours * rates[s.staff_member_id])
        assert 6.5 <= s.actual_hours <= 11.5
    overtime = [s for s in done if s.actual_hours > 8]
    assert 0 < len(overtime) < 0.2 * len(done)
    weekdays = {s.shift_date.weekday() for s in done}
    assert weekdays == set(range(7))


def test_branches_never_mix(demo):
    db, _ = demo
    r1, r2 = [r.id for r in _branches(db)]
    item_owner = {m.id: m.restaurant_id for m in db.query(models.MenuItem).all()}
    for oi in db.query(models.OrderItem).join(models.Order).filter(models.Order.restaurant_id == r1).limit(500):
        assert item_owner[oi.menu_item_id] == r1
    inv_owner = {i.id: i.restaurant_id for i in db.query(models.InventoryItem).all()}
    for po in db.query(models.PurchaseOrder).all():
        assert inv_owner[po.inventory_item_id] == po.restaurant_id
        assert db.get(models.Supplier, po.supplier_id).restaurant_id == po.restaurant_id
    assert db.query(models.Order).filter(models.Order.restaurant_id == r2).count() > 1000


def test_weekday_patterns_follow_the_calendar(demo):
    db, _ = demo
    by_weekday = Counter()
    days = {}
    for (created,) in db.query(models.Order.created_at).filter(models.Order.status != models.OrderStatus.CANCELLED):
        d = eat_date(created)
        by_weekday[d.weekday()] += 1
        days.setdefault(d.weekday(), set()).add(d)
    mean = {w: by_weekday[w] / len(days[w]) for w in range(7)}
    assert mean[5] > mean[0] * 1.4 and mean[4] > mean[1] * 1.3          # Saturday and Friday are the busy days, Monday and Tuesday quiet


# ═════════════════════════════════════════════════════════════════════════════
# Honesty: nothing that could be mistaken for a real record
# ═════════════════════════════════════════════════════════════════════════════

def test_no_payment_reference_and_no_dialable_phone_number(demo):
    db, _ = demo
    assert db.query(models.Order).filter(models.Order.mpesa_receipt.isnot(None)).count() == 0
    assert db.query(models.Order).filter(models.Order.mpesa_checkout_request_id.isnot(None)).count() == 0
    from phone_utils import normalize_phone
    phones = {p for (p,) in db.query(models.Order.customer_phone).distinct() if p} | {p for (p,) in db.query(models.Reservation.customer_phone).distinct() if p}
    assert phones
    for p in phones:
        assert p.startswith("+25400") and normalize_phone(p) == p       # Kenyan mobiles start 2547 / 2541: these can never reach anyone
    assert all(not s.contact_phone for s in db.query(models.Supplier))


def test_the_staff_logins_have_a_password_nobody_knows(demo):
    db, _ = demo
    import auth
    users = db.query(models.User).filter(models.User.email.like("%@demo-restaurant.example"), models.User.email != OWNER).all()
    assert {u.staff_role for u in users} == {
        models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN, models.StaffRole.CONTROLLER,
    }
    for u in users:
        for guess in (PASSWORD, "password", "demo", "Demo-Passw0rd!x1", u.email):
            assert not auth.verify_password(guess, u.hashed_password)


def test_the_demo_owner_has_chosen_two_targets(demo):
    db, _ = demo
    from owner.settings import describe
    for r in _branches(db):
        d = describe(db, r.id)
        assert d["chosen"] and len([f for f in d["fields"] if not f["is_default"]]) == 2
    assert db.query(models.RestaurantSettingsAudit).count() >= 4


# ═════════════════════════════════════════════════════════════════════════════
# Determinism and idempotency
# ═════════════════════════════════════════════════════════════════════════════

def test_same_seed_same_rows_and_a_reseed_neither_duplicates_nor_drifts(db_session):
    first = build(db_session, OWNER, PASSWORD, now=NOW)
    fp1 = fingerprint(db_session)
    tenants1 = db_session.query(models.Tenant).count()
    users1 = {u.email: (u.id, u.hashed_password) for u in db_session.query(models.User)}
    restaurants1 = [r.id for r in _branches(db_session)]

    second = build(db_session, OWNER, PASSWORD, now=NOW)
    assert fingerprint(db_session) == fp1
    assert second.counts == first.counts
    assert db_session.query(models.Tenant).count() == tenants1
    assert [r.id for r in _branches(db_session)] == restaurants1              # the restaurants are reused, not recreated
    assert {u.email: (u.id, u.hashed_password) for u in db_session.query(models.User)} == users1      # no new logins, no rotated passwords
    assert second.wiped["orders"] == first.counts["orders"]                   # the second run replaced the first run's rows
    assert db_session.query(models.Order).count() == first.counts["orders"]
    assert db_session.query(models.Organization).count() == 1 and db_session.query(models.Region).count() == 1
    assert db_session.query(models.RestaurantSettings).count() == 2


def test_reseed_keeps_the_hash_when_the_env_password_is_unchanged(db_session, monkeypatch):
    """A staff password from the environment must not rotate on reseed: bcrypt salts a new hash every time."""
    monkeypatch.setenv("DEMO_RESTAURANT_MANAGER_PASSWORD", "Manager-pass-1")
    for name in ("DEMO_RESTAURANT_STOREKEEPER_PASSWORD", "DEMO_RESTAURANT_KITCHEN_PASSWORD", "DEMO_RESTAURANT_ACCOUNTANT_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    from tenant_provisioning import ensure_demo_restaurant, upsert_demo_staff
    ensure_demo_restaurant(db_session, OWNER, PASSWORD)
    manager = db_session.query(models.User).filter_by(email="manager@demo-restaurant.example").one()
    first = manager.hashed_password
    tenant = db_session.query(models.Tenant).one()
    upsert_demo_staff(db_session, tenant, manager.active_restaurant_id, reset_password=True)
    assert manager.hashed_password == first
    import auth
    assert auth.verify_password("Manager-pass-1", manager.hashed_password)


def test_a_different_seed_gives_different_rows(db_session):
    build(db_session, OWNER, PASSWORD, now=NOW, seed=1)
    a = fingerprint(db_session)
    build(db_session, OWNER, PASSWORD, now=NOW, seed=2)
    assert fingerprint(db_session) != a


def test_dates_are_relative_to_now(db_session):
    a = build(db_session, OWNER, PASSWORD, now=NOW)
    later = NOW + timedelta(days=7)
    b = build(db_session, OWNER, PASSWORD, now=later)
    last = db_session.query(func.max(models.Order.created_at)).scalar()
    assert last <= later and last > NOW                                      # the data moved forward with the clock
    assert a.counts["orders"] > 3000 and b.counts["orders"] > 3000


# ═════════════════════════════════════════════════════════════════════════════
# Safety
# ═════════════════════════════════════════════════════════════════════════════

def _other_tenant(db):
    t = models.Tenant(name="Somebody Else's Grill")
    db.add(t)
    db.flush()
    r = models.Restaurant(tenant_id=t.id, name="Somebody Else's Grill", address="x")
    db.add(r)
    db.flush()
    m = models.MenuItem(restaurant_id=r.id, name="Real dish", price=1000, cost_price=500, category="x")
    db.add(m)
    inv = models.InventoryItem(restaurant_id=r.id, item_name="Real flour", unit="kg", quantity=5, cost_per_unit_cents=100, low_stock_threshold=1)
    db.add(inv)
    db.flush()
    o = models.Order(restaurant_id=r.id, total=1000, created_at=NOW, is_paid=True, status=models.OrderStatus.SERVED)
    db.add(o)
    db.flush()
    db.add(models.OrderItem(order_id=o.id, menu_item_id=m.id, quantity=1, unit_price=1000))
    db.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.OUT, quantity=1, reason="x"))
    db.commit()
    return t, r


def _counts(db, rid):
    return {"orders": db.query(models.Order).filter(models.Order.restaurant_id == rid).count(),
            "items": db.query(models.OrderItem).join(models.Order).filter(models.Order.restaurant_id == rid).count(),
            "menu": db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == rid).count(),
            "inv": db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == rid).count(),
            "moves": db.query(models.StockMovement).join(models.InventoryItem).filter(models.InventoryItem.restaurant_id == rid).count()}


def test_reseeding_never_touches_another_tenants_rows(db_session):
    other, rest = _other_tenant(db_session)
    before = _counts(db_session, rest.id)
    build(db_session, OWNER, PASSWORD, now=NOW)
    build(db_session, OWNER, PASSWORD, now=NOW)
    assert _counts(db_session, rest.id) == before == {"orders": 1, "items": 1, "menu": 1, "inv": 1, "moves": 1}
    assert db_session.query(models.Tenant).filter(models.Tenant.id == other.id).count() == 1


def test_only_the_demo_tenant_can_be_wiped(db_session):
    other, rest = _other_tenant(db_session)
    before = _counts(db_session, rest.id)
    with pytest.raises(WipeRefused):
        wipe_demo(db_session, other)
    with pytest.raises(WipeRefused):
        wipe_demo(db_session, None)
    renamed = models.Tenant(name="Demo Restaurant Two")
    db_session.add(renamed)
    db_session.flush()
    with pytest.raises(WipeRefused):
        wipe_demo(db_session, renamed)
    assert _counts(db_session, rest.id) == before


def test_wipe_leaves_the_tenant_restaurants_and_users_in_place(fresh_demo):
    db, _ = fresh_demo
    tenant = db.query(models.Tenant).filter(models.Tenant.name == "Demo Restaurant").one()
    users, restaurants = db.query(models.User).count(), db.query(models.Restaurant).count()
    wiped = wipe_demo(db, tenant)
    assert wiped["orders"] > 0 and wiped["stock_movements"] > 0 and wiped["prep_times"] > 0 and wiped["menu_ingredients"] > 0
    assert db.query(models.Order).count() == db.query(models.OrderItem).count() == db.query(models.MenuItem).count() == 0
    assert db.query(models.User).count() == users and db.query(models.Restaurant).count() == restaurants
    assert db.query(models.Tenant).count() == 1


def test_every_table_that_hangs_off_a_restaurant_is_wiped_or_deliberately_kept():
    """A model added later with a restaurant_id must be classified here, or this test fails — so it cannot be left behind
    as stale rows after a re-seed, nor deleted without anybody deciding that it should be."""
    tables = models.Base.metadata.tables
    scoped = {name for name, t in tables.items() if "restaurant_id" in t.c} - {"restaurants"}
    assert scoped == set(WIPED) | set(KEPT) | {"orders", "inventory_items", "menu_items", "suppliers"} | (set(WIPED) & scoped)
    assert not (set(WIPED) & set(KEPT))
    children = {name for name, t in tables.items() if name not in scoped and name != "restaurants"
                and any(fk.column.table.name in scoped for c in t.c for fk in c.foreign_keys)}
    handled = {"order_items", "prep_times", "stock_movements", "menu_ingredients", "workflow_steps", "owner_os_messages", "team_workflow_events"} | set(KEPT_CHILDREN)
    assert children <= handled | {"prep_times"}, f"child tables with no wipe decision: {children - handled}"
    assert all(KEPT.values()) and all(KEPT_CHILDREN.values()), "every kept table needs a written reason"


# ── the CLI guard ────────────────────────────────────────────────────────────

def _script():
    spec = importlib.util.spec_from_file_location("reseed_demo", ROOT / "execution" / "reseed_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("url,kind", [
    ("sqlite:///./x.db", "local"), ("sqlite:////tmp/x.db", "local"), ("sqlite://", "local"),
    ("postgresql://u:p@localhost:5432/db", "local"), ("postgresql+psycopg2://u:p@127.0.0.1/db", "local"), ("postgresql://u:p@[::1]/db", "local"),
    ("postgresql://u:p@ep-cool-name.us-east-2.aws.neon.tech/db", "remote"), ("postgres://u:p@containers-us-west-1.railway.app:5432/railway", "remote"),
    ("postgresql://u:p@10.0.0.5/db", "remote"), ("", "remote"), ("mysql://u:p@localhost/db", "remote"),
])
def test_databases_are_local_or_remote(url, kind):
    assert safety.classify(url) == kind


def test_nothing_runs_without_yes_and_a_remote_database_needs_four_more_things():
    local = "sqlite:///./x.db"
    remote = "postgresql://user:secret@ep-cool-name.us-east-2.aws.neon.tech/db"
    with pytest.raises(safety.UnsafeTarget, match="--yes"):
        safety.require_safe_target(local, yes=False)
    assert safety.require_safe_target(local, yes=True) == "local"
    for kwargs in ({}, {"allow_remote": True}, {"allow_remote": True, "typed": "RESEED DEMO wrong-host"},
                   {"allow_remote": True, "typed": safety.required_sentence(remote)}):
        with pytest.raises(safety.UnsafeTarget) as err:
            safety.require_safe_target(remote, yes=True, env={}, **kwargs)
        assert "secret" not in str(err.value) and "ep-cool-name" in str(err.value)     # credentials are never echoed
    assert safety.require_safe_target(remote, yes=True, allow_remote=True, typed=safety.required_sentence(remote),
                                      env={"ALLOW_DESTRUCTIVE": "1"}) == "remote"
    assert safety.describe(remote) == "postgresql://ep-cool-name.us-east-2.aws.neon.tech/db"


def test_the_cli_refuses_a_remote_database_and_never_reads_the_dotenv_for_its_target(monkeypatch, capsys):
    script = _script()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/db")
    assert script.main(["--yes", "--owner-password", PASSWORD]) == 2
    assert "not a local database" in capsys.readouterr().err
    assert script.main(["--yes", "--allow-remote", "--owner-password", PASSWORD]) == 2        # no typed sentence on a non-tty
    assert script.main(["--owner-password", PASSWORD]) == 2                                   # no --yes
    assert script.main(["--dry-run"]) == 0                                                     # writes nothing
    assert "(remote)" in capsys.readouterr().out
    source = (ROOT / "execution" / "reseed_demo.py").read_text()
    assert "load_dotenv" not in source.replace("NEVER read", "")


def test_the_cli_reseeds_a_local_sqlite_file(tmp_path, monkeypatch, capsys):
    script = _script()
    url = f"sqlite:///{tmp_path / 'demo.db'}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = script.main(["--database-url", url, "--yes", "--owner-password", PASSWORD, "--days", "14"])
    out = capsys.readouterr().out
    assert code == 0 and '"orders"' in out
    import sqlalchemy as sa
    with sa.create_engine(url).connect() as conn:
        assert conn.execute(sa.text("select count(*) from tenants where name = 'Demo Restaurant'")).scalar() == 1
        assert conn.execute(sa.text("select count(*) from restaurants")).scalar() == 2
        assert conn.execute(sa.text("select count(*) from orders")).scalar() > 100


# ═════════════════════════════════════════════════════════════════════════════
# The point of it: every built engine in the registry has real output on the demo
# ═════════════════════════════════════════════════════════════════════════════

# engine key -> (Home block path, what "real output" means). Evaluated on the live demo (engines read the real clock).
def _has(block, *fields):
    return block["state"] in ("live", "as_entered") and all(block.get(f) for f in fields)


OUTPUT = {
    "sales_summary": ("pulse", lambda b: b["state"] == "live" and b["sales_in_period"] > 0 and len(b["trend_7d"]) == 7),
    "revenue_forecast": ("sales_dishes.forecast", lambda b: _has(b, "next_7_days", "actual")),
    "profit": ("money.cost_dials", lambda b: b["state"] == "live" and 20 < b["food_cost_pct"] < 40 and b["wages_pct"]),
    "pricing": ("sales_dishes.price_ideas", lambda b: _has(b, "ideas")),
    "menu": ("sales_dishes.matrix", lambda b: _has(b, "dishes") and len({d["kind"] for d in b["dishes"]}) >= 3),
    "simulator": ("sales_dishes.simulator", lambda b: b["state"] == "live"),
    "inventory": ("store.reorder", lambda b: b["state"] in ("live", "as_entered") and b["tracked"] >= 30 and b["least_cover"]
                  and all(i["days_left"] is not None for i in b["least_cover"])),
    "custody": ("store.missing", lambda b: _has(b, "items")),
    "cash": ("cash.shifts", lambda b: _has(b, "shifts")),
    "mpesa_match": ("cash.mpesa", lambda b: b["state"] == "not_from_pos" and b["checked"]["sales"] > 15 and b["matched"]["count"] > 15 and b["headline"]),
    "fraud": ("cash.cancelled_sales", lambda b: b["state"] == "live" and b["cancelled_last_7_days"] >= 0 and "to_check" in b),
    "kds": ("staff.kitchen", lambda b: _has(b, "stations")),
    "reservations": ("coming_up.bookings", lambda b: b["state"] == "live" and (b["covers_today"] > 0 or len(b["next_days"]) >= 3)),
    "labor": ("staff.wages", lambda b: _has(b, "by_person") and b["wages_pct"] > 0),
    "supply_chain": ("store.suppliers", lambda b: _has(b, "suppliers") and any(s["on_time_pct"] is not None for s in b["suppliers"])),
    "marketing": ("sales_dishes.win_back", lambda b: b["state"] == "live" and b["lapsed_guests"] > 0 and b["reachable"] > 0),
    "roi": ("money.savings", lambda b: b["state"] == "live" and b["captured_kes_month"] > 0 and b["hours_saved_30d"] > 0),
    "twin": ("sales_dishes.outlook", lambda b: b["state"] == "live" and b["next_30_days"] > 0),
    "data_quality": ("permits.data_trust", lambda b: b["state"] == "live" and b["dishes"] == len(cat.MENU)),
    "decisions": ("costing_you_money", lambda b: b["state"] == "live" and len(b["cards"]) >= 3),
    "owner_settings": ("permits.settings", lambda b: b["state"] == "as_entered" and b["changed"] == 2),
    "money": ("money.pnl", lambda b: b["state"] == "as_entered" and b["complete"] in (True, False) and b["lines"][-1]["kes"] != 0
              and any(s["key"] == "premises" for s in b["sections"])),
}


@pytest.fixture(scope="module")
def live_demo(tmp_path_factory):
    """The demo built against the real clock, so the engines' own 'now' agrees with the generator's."""
    engine, db = _scratch_session(tmp_path_factory, "live")
    summary = build(db, OWNER, PASSWORD, now=utcnow(), plant=())
    from owner.home import compose_home
    from owner.states import OwnerContext
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    restaurant = db.get(models.Restaurant, summary.restaurant_ids[0])
    yield db, compose_home(OwnerContext(db, owner, restaurant), "7d"), summary
    db.close()
    engine.dispose()


def _block(home, path):
    parts = path.split(".")
    if len(parts) == 1:
        return home[parts[0]]
    head, name = parts
    return home["coming_up"][name] if head == "coming_up" else home["areas"][head]["blocks"][name]


def test_every_built_engine_has_real_output_on_the_demo(live_demo):
    from owner.registry import engines
    _db, home, _s = live_demo
    built = {e.key for e in engines("built")}
    assert built - {"strategist"} <= set(OUTPUT), f"no output check for: {built - {'strategist'} - set(OUTPUT)}"
    failures = []
    for key, (path, ok) in OUTPUT.items():
        block = _block(home, path)
        try:
            good = ok(block)
        except Exception as exc:  # noqa: BLE001
            good = False
            block = {"error": repr(exc), **{k: v for k, v in block.items() if not isinstance(v, (list, dict))}}
        if not good:
            failures.append((key, path, {k: v for k, v in block.items() if not isinstance(v, (list, dict))}))
    assert failures == [], f"engines with no output on the demo: {json.dumps(failures, default=str, indent=1)}"


def test_the_demo_is_not_in_trouble_on_day_one(live_demo):
    """A calm baseline: the first things an owner sees are not alarms. (Planted problems arrive in S2.2.)"""
    _db, home, _s = live_demo
    assert home["areas"]["cash"]["summary"]["status"] == "good"
    assert home["areas"]["money"]["summary"]["word"] == "Fine"
    assert home["areas"]["store"]["blocks"]["missing"]["state"] == "as_entered"
    assert not [i for i in home["areas"]["store"]["blocks"]["missing"]["items"] if i["check"]]
    assert home["pulse"]["freshness"]["is_stale"] is False


def test_home_on_the_demo_is_fast_enough_to_use(live_demo):
    import time
    from owner.home import compose_home
    from owner.states import OwnerContext
    db, _home, summary = live_demo
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    t0 = time.perf_counter()
    compose_home(OwnerContext(db, owner, db.get(models.Restaurant, summary.restaurant_ids[0])), "30d")
    elapsed = time.perf_counter() - t0
    print(f"\n[S2.1] /owner/home (30d) on the 120-day, 3.5k-order demo branch: {elapsed * 1000:.0f} ms")
    assert elapsed < 20


def test_no_unplanted_cost_line_can_look_like_a_spike_on_any_day():
    """The demo is built relative to today, so its ordinary noise changes with the date. P9 (gas) is the only planted spike:
    every other line must stay under the owner's default 25% however the noise falls (one month at +s against three at −s)."""
    from demo.generator import DemoBuilder
    from owner.settings import DEFAULTS
    worst = max((1 + spread) / (1 - spread) for *_rest, spread in DemoBuilder.LEDGER)
    assert worst < 1 + DEFAULTS.expense_spike_pct / 100, worst


def test_the_demo_statement_starts_at_a_nairobi_midnight_whatever_the_hour():
    """A statement is exported for whole days and the matcher reads it that way (coverage starts at midnight Nairobi of the first payment's day, S6.2
    decision b). The demo's statement used to start at "now minus 14 days", a moment that moves through the day: a sale on that first day earlier
    than the hour of the build was left off the statement yet counted as covered, so the gap read 4 instead of the planted 3 after about noon in
    Nairobi (found by running the gate in the afternoon). The start may move only when the Nairobi date does."""
    from demo.generator import P8_DAYS, statement_window
    from time_utils import EAT_OFFSET, eat_date
    base = datetime(2026, 10, 28)
    starts = set()
    for hour in range(24):
        now = base + timedelta(hours=hour, minutes=17)
        since, until = statement_window(now)
        assert since + EAT_OFFSET == datetime.combine(eat_date(now - timedelta(days=P8_DAYS)), datetime.min.time()), (hour, since)
        assert (since + EAT_OFFSET).time() == datetime.min.time()
        assert until == now - timedelta(minutes=45)
        starts.add(since)
    assert len(starts) == 2                       # one start before Nairobi midnight (21:00 UTC), the next day's after
