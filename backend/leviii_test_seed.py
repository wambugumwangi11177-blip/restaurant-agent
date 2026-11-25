"""Idempotent Eleven test stack for Jack deployments (env-gated).

Set SEED_TEST_DATA=1 on test stacks only. Production leaves it unset — no-op.
"""
from __future__ import annotations

import base64
import logging
import os

import auth
import models
from fastapi import HTTPException
from models import Role, StaffRole, StaffSetupProgress
from routers.store_intake import ensure_zones
from sqlalchemy.orm import Session
from staff_audit import record_entry

logger = logging.getLogger("leviii_test_seed")

# Minimal valid JPEG for demo evidence photos in test stacks.
_DEMO_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
    "CAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAA"
    "AAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB"
    "AAIRAxEAPwCdABmX/9k="
)

ELEVEN = "Eleven"
TEST_TENANT = "Test Restaurant"
SUPERADMIN_EMAIL = "wambugu@leviii.ai"
TEST_OWNER_EMAIL = "owner@test.restaurant.leviii"
OWNER_EMAIL = "owner@eleven.leviii"
OWNER_RESET_MARKER = "eleven_test_owner_first_login_reset"
STAFF = (
    ("jack@eleven.leviii", StaffRole.STOCKKEEPER, "Jack"),
    ("amina@eleven.leviii", StaffRole.CONTROLLER, "Amina"),
)
EMPTY_OWNER_EMAIL = "owner-empty@eleven.leviii"
EMPTY_WALL_STAFF = (
    ("jack-empty@eleven.leviii", StaffRole.STOCKKEEPER, "Jack"),
    ("amina-empty@eleven.leviii", StaffRole.CONTROLLER, "Amina"),
)


class SeedError(Exception):
    pass


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _reset_marker_applied(db: Session, owner_id: int) -> bool:
    return (
        db.query(models.StaffEntryAudit)
        .filter(
            models.StaffEntryAudit.action == OWNER_RESET_MARKER,
            models.StaffEntryAudit.entity_id == owner_id,
        )
        .first()
        is not None
    )


def ensure_eleven_test_data(
    db: Session,
    owner_password: str,
    *,
    owner_first_login: bool = False,
    owner_reset_first_login: bool = False,
) -> list[str]:
    """Create Eleven owner, Jack, accountant, zones, and a little stock if missing."""
    if not owner_first_login and owner_password:
        try:
            auth.require_strong_password(owner_password)
        except HTTPException as exc:
            raise SeedError(exc.detail) from exc

    log: list[str] = []
    tenant = db.query(models.Tenant).filter(models.Tenant.name == ELEVEN).first()
    if tenant is None:
        tenant = models.Tenant(name=ELEVEN)
        db.add(tenant)
        db.flush()
        log.append(f"[CREATED] tenant {ELEVEN!r}")
    else:
        log.append(f"[EXISTS] tenant {ELEVEN!r}")

    restaurant = db.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).first()
    if restaurant is None:
        restaurant = models.Restaurant(tenant_id=tenant.id, name=ELEVEN, address="Ngong Road")
        db.add(restaurant)
        db.flush()
        log.append("[CREATED] restaurant Eleven")
    else:
        log.append("[EXISTS] restaurant Eleven")

    owner = db.query(models.User).filter(models.User.email == OWNER_EMAIL).first()
    if owner is None:
        if owner_first_login:
            hashed = None
            must_change = True
            log.append(f"[CREATED] owner {OWNER_EMAIL} (first login — no password)")
        else:
            if not owner_password:
                raise SeedError("SEED_OWNER_PASSWORD is required when SEED_OWNER_FIRST_LOGIN is off")
            hashed = auth.get_password_hash(owner_password)
            must_change = False
            log.append(f"[CREATED] owner {OWNER_EMAIL}")
        owner = models.User(
            email=OWNER_EMAIL,
            hashed_password=hashed,
            role=Role.ADMIN,
            staff_role=StaffRole.OWNER,
            tenant_id=tenant.id,
            must_change_password=must_change,
            is_email_verified=True,
            is_active=True,
        )
        db.add(owner)
        db.flush()
    else:
        owner.role = Role.ADMIN
        owner.staff_role = StaffRole.OWNER
        owner.is_active = True
        if (
            owner_reset_first_login
            and owner.hashed_password
            and not _reset_marker_applied(db, owner.id)
        ):
            owner.hashed_password = None
            owner.must_change_password = True
            record_entry(
                db,
                restaurant.id,
                owner,
                OWNER_RESET_MARKER,
                "system",
                "Owner password cleared once for Jack test first-login.",
                entity_id=owner.id,
                detail={"email": OWNER_EMAIL},
            )
            log.append(f"[RESET] owner {OWNER_EMAIL} (first login, one-time)")
        else:
            log.append(f"[EXISTS] owner {OWNER_EMAIL} (password unchanged)")
    owner.active_restaurant_id = restaurant.id

    for email, role, name in STAFF:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            user = models.User(
                email=email,
                hashed_password=None,
                role=Role.STAFF,
                staff_role=role,
                tenant_id=tenant.id,
                must_change_password=True,
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(StaffSetupProgress(user_id=user.id, restaurant_id=restaurant.id))
            log.append(f"[CREATED] staff login {email}")
        else:
            log.append(f"[EXISTS] staff login {email}")
        user.active_restaurant_id = restaurant.id
        user.tenant_id = tenant.id
        if (
            db.query(models.StaffMember)
            .filter(models.StaffMember.restaurant_id == restaurant.id, models.StaffMember.user_id == user.id)
            .first()
            is None
        ):
            db.add(
                models.StaffMember(
                    restaurant_id=restaurant.id,
                    user_id=user.id,
                    name=name,
                    role_title=role.value,
                )
            )
            log.append(f"[CREATED] staff member {name}")

    zones_before = db.query(models.StockZone).filter(models.StockZone.restaurant_id == restaurant.id).count()
    ensure_zones(db, restaurant.id)
    if zones_before == 0:
        log.append("[CREATED] default storage zones")

    if (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id)
        .first()
        is None
    ):
        db.add(
            models.InventoryItem(
                restaurant_id=restaurant.id,
                item_name="Rice",
                quantity=12,
                unit="kg",
                cost_per_unit=0,
                low_stock_threshold=2,
            )
        )
        log.append("[CREATED] sample stock (Rice)")

    if db.query(models.Supplier).filter(models.Supplier.restaurant_id == restaurant.id).first() is None:
        db.add(
            models.Supplier(
                restaurant_id=restaurant.id,
                name="Fresh Farm",
                contact_phone="0700111222",
                contact_email="",
                notes="Sample supplier for Jack test",
            )
        )
        log.append("[CREATED] sample supplier")

    rice = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id, models.InventoryItem.item_name == "Rice")
        .first()
    )
    supplier = db.query(models.Supplier).filter(models.Supplier.restaurant_id == restaurant.id).first()
    if rice and supplier:
        rice.cost_per_unit = 560
        rice.default_supplier_id = supplier.id
        rice.par_level = 20
        rice.low_stock_threshold = 5
        restaurant.restock_routing_mode = "owner_approves"
    has_v12_pilau = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.restaurant_id == restaurant.id, models.MenuItem.name == "Pilau")
        .first()
    )
    pilau = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.restaurant_id == restaurant.id, models.MenuItem.name == "Pilau (demo)")
        .first()
    )
    if pilau is None and rice is not None and has_v12_pilau is None:
        pilau = models.MenuItem(
            restaurant_id=restaurant.id,
            name="Pilau (demo)",
            category="Kitchen",
            price=45000,
            cost_price=14000,
        )
        db.add(pilau)
        db.flush()
        db.add(
            models.MenuIngredient(
                menu_item_id=pilau.id,
                inventory_item_id=rice.id,
                quantity_per_serving=0.25,
                recipe_unit="kg",
                yield_fraction=1.0,
            )
        )
        log.append("[CREATED] demo dish Pilau (demo)")
    jack_user = db.query(models.User).filter(models.User.email == STAFF[0][0]).first()
    amina_user = db.query(models.User).filter(models.User.email == STAFF[1][0]).first()
    staff_pass = os.getenv("SEED_STAFF_PASSWORD", "JackTestPass1!")
    for user in (jack_user, amina_user):
        if user and staff_pass:
            user.hashed_password = auth.get_password_hash(staff_pass)
            user.must_change_password = False
            log.append(f"[SET] password for {user.email}")

    if db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant.id, models.Order.notes.contains("[DEMO]")
    ).first() is None and pilau:
        order = models.Order(
            restaurant_id=restaurant.id,
            status=models.OrderStatus.SERVED,
            order_type=models.OrderType.DINE_IN,
            is_paid=True,
            total=45000,
            notes="[DEMO] test till ticket",
        )
        db.add(order)
        db.flush()
        db.add(models.OrderItem(order_id=order.id, menu_item_id=pilau.id, quantity=12, unit_price=45000))
        log.append("[CREATED] demo sales for dishes/money screens")

    _refresh_demo_feed(db, restaurant, owner, jack_user, amina_user, rice, supplier, pilau, log)

    db.commit()

    # Test Restaurant — proves the data wall (no shared stock with Eleven).
    test_tenant = db.query(models.Tenant).filter(models.Tenant.name == TEST_TENANT).first()
    if test_tenant is None:
        test_tenant = models.Tenant(name=TEST_TENANT)
        db.add(test_tenant)
        db.flush()
        log.append(f"[CREATED] tenant {TEST_TENANT!r}")
    test_restaurant = (
        db.query(models.Restaurant).filter(models.Restaurant.tenant_id == test_tenant.id).first()
    )
    if test_restaurant is None:
        test_restaurant = models.Restaurant(
            tenant_id=test_tenant.id,
            name=TEST_TENANT,
            address="Wall test only",
        )
        db.add(test_restaurant)
        db.flush()
        log.append("[CREATED] restaurant Test Restaurant")
    test_owner = db.query(models.User).filter(models.User.email == TEST_OWNER_EMAIL).first()
    if test_owner is None:
        test_owner = models.User(
            email=TEST_OWNER_EMAIL,
            hashed_password=None,
            role=Role.ADMIN,
            staff_role=StaffRole.OWNER,
            tenant_id=test_tenant.id,
            must_change_password=True,
            is_active=True,
            is_email_verified=True,
        )
        db.add(test_owner)
        db.flush()
        log.append(f"[CREATED] test owner {TEST_OWNER_EMAIL} (first login)")
    test_owner.active_restaurant_id = test_restaurant.id

    empty_restaurant = (
        db.query(models.Restaurant)
        .filter(models.Restaurant.tenant_id == tenant.id, models.Restaurant.name == "Eleven (empty)")
        .first()
    )
    if empty_restaurant is None:
        empty_restaurant = models.Restaurant(
            tenant_id=tenant.id,
            name="Eleven (empty)",
            address="No demo data — screenshot empty state",
        )
        db.add(empty_restaurant)
        db.flush()
        log.append("[CREATED] empty Eleven restaurant for EMPTY captures")
    ensure_zones(db, empty_restaurant.id)

    empty_owner = db.query(models.User).filter(models.User.email == EMPTY_OWNER_EMAIL).first()
    if empty_owner is None:
        if owner_password:
            empty_owner = models.User(
                email=EMPTY_OWNER_EMAIL,
                hashed_password=auth.get_password_hash(owner_password),
                role=Role.ADMIN,
                staff_role=StaffRole.OWNER,
                tenant_id=tenant.id,
                must_change_password=False,
                is_active=True,
                is_email_verified=True,
            )
            db.add(empty_owner)
            db.flush()
            log.append(f"[CREATED] empty-stack owner {EMPTY_OWNER_EMAIL}")
    if empty_owner:
        empty_owner.active_restaurant_id = empty_restaurant.id
        empty_owner.tenant_id = tenant.id
    _ensure_empty_wall_stack(db, tenant, empty_restaurant, empty_owner, owner_password, log)
    _ensure_empty_wall_no_sales(db, empty_restaurant, log)
    _ensure_pos_source_bindings(db, restaurant.id, empty_restaurant.id, log)

    super_user = db.query(models.User).filter(models.User.email == SUPERADMIN_EMAIL).first()
    if super_user is None:
        if not owner_password and not owner_first_login:
            log.append(f"[SKIP] super-admin {SUPERADMIN_EMAIL} (needs SEED_OWNER_PASSWORD on first run)")
        else:
            super_user = models.User(
                email=SUPERADMIN_EMAIL,
                hashed_password=auth.get_password_hash(owner_password) if owner_password else None,
                role=Role.SUPERADMIN,
                staff_role=StaffRole.OWNER,
                tenant_id=tenant.id,
                must_change_password=bool(owner_first_login and not owner_password),
                is_active=True,
                is_email_verified=True,
            )
            db.add(super_user)
            log.append(f"[CREATED] super-admin {SUPERADMIN_EMAIL}")
    else:
        super_user.role = Role.SUPERADMIN
        log.append(f"[EXISTS] super-admin {SUPERADMIN_EMAIL}")

    db.commit()
    return log


def _ensure_pos_source_bindings(
    db: Session,
    demo_restaurant_id: int,
    empty_restaurant_id: int,
    log: list[str],
) -> None:
    """Demo till stays on `quicksell`; empty-wall audit uses `quicksell-empty` (+ webhook header)."""
    from integration.inbox_models import PosSourceBinding

    for slug, restaurant_id in (
        ("quicksell", demo_restaurant_id),
        ("quicksell-empty", empty_restaurant_id),
    ):
        row = db.query(PosSourceBinding).filter_by(slug=slug).first()
        if row is None:
            db.add(PosSourceBinding(slug=slug, restaurant_id=restaurant_id))
            log.append(f"[CREATED] POS binding {slug}")
        elif row.restaurant_id != restaurant_id:
            row.restaurant_id = restaurant_id
            log.append(f"[SYNC] POS binding {slug}")


def _ensure_empty_wall_stack(
    db: Session,
    test_tenant: models.Tenant,
    test_restaurant: models.Restaurant,
    test_owner: models.User | None,
    owner_password: str,
    log: list[str],
) -> None:
    """Fresh Eleven restaurant for EMPTY screenshots — no demo rows, Jack setup incomplete."""
    from time_utils import utcnow

    now = utcnow()
    staff_pass = os.getenv("SEED_STAFF_PASSWORD", "JackTestPass1!").strip()
    owner_pin = os.getenv("SEED_OWNER_PIN", "2468")
    staff_pin = os.getenv("SEED_STAFF_PIN", "1357")

    if test_owner and owner_password:
        test_owner.hashed_password = auth.get_password_hash(owner_password)
        test_owner.must_change_password = False
        test_owner.is_active = True
        if not test_owner.hashed_pin:
            test_owner.hashed_pin = auth.get_pin_hash(owner_pin)
        log.append(f"[SYNC] empty-wall owner {test_owner.email}")

    for email, role, name in EMPTY_WALL_STAFF:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            user = models.User(
                email=email,
                hashed_password=auth.get_password_hash(staff_pass) if staff_pass else None,
                role=Role.STAFF,
                staff_role=role,
                tenant_id=test_tenant.id,
                must_change_password=False,
                is_active=True,
                is_email_verified=True,
            )
            db.add(user)
            db.flush()
            log.append(f"[CREATED] empty-wall staff {email}")
        user.active_restaurant_id = test_restaurant.id
        user.tenant_id = test_tenant.id
        if staff_pass:
            user.hashed_password = auth.get_password_hash(staff_pass)
            user.must_change_password = False
        if not user.hashed_pin:
            user.hashed_pin = auth.get_pin_hash(staff_pin)

        member = (
            db.query(models.StaffMember)
            .filter(models.StaffMember.restaurant_id == test_restaurant.id, models.StaffMember.user_id == user.id)
            .first()
        )
        if member is None:
            db.add(
                models.StaffMember(
                    restaurant_id=test_restaurant.id,
                    user_id=user.id,
                    name=name,
                    role_title=role.value,
                )
            )

        db.query(models.StaffSetupAnswer).filter(models.StaffSetupAnswer.user_id == user.id).delete(synchronize_session=False)

        progress = db.query(StaffSetupProgress).filter(StaffSetupProgress.user_id == user.id).first()
        if progress is None:
            progress = StaffSetupProgress(user_id=user.id, restaurant_id=test_restaurant.id)
            db.add(progress)
            db.flush()
        progress.account_completed_at = now
        progress.recipes_completed_at = None
        progress.questionnaire_completed_at = None
        progress.updated_at = now


def sync_test_stack_credentials(db: Session) -> list[str]:
    """Re-sync known test passwords and clear login lockouts (backend-test only)."""
    if not _truthy("SEED_TEST_DATA"):
        return []
    if _truthy("SEED_OWNER_FIRST_LOGIN"):
        return []
    log: list[str] = []
    owner_pass = os.getenv("SEED_OWNER_PASSWORD", "").strip()
    staff_pass = os.getenv("SEED_STAFF_PASSWORD", "JackTestPass1!").strip()
    empty_emails = [EMPTY_OWNER_EMAIL, *(s[0] for s in EMPTY_WALL_STAFF)]
    for email in (OWNER_EMAIL, TEST_OWNER_EMAIL, *(s[0] for s in STAFF), *empty_emails):
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            continue
        if user.locked_until or user.failed_login_attempts:
            user.locked_until = None
            user.failed_login_attempts = 0
            log.append(f"[UNLOCK] {email}")
        if email in (OWNER_EMAIL, TEST_OWNER_EMAIL, EMPTY_OWNER_EMAIL) and owner_pass:
            user.hashed_password = auth.get_password_hash(owner_pass)
            user.must_change_password = False
            pin = os.getenv("SEED_OWNER_PIN", "2468")
            if not user.hashed_pin:
                user.hashed_pin = auth.get_pin_hash(pin)
                log.append("[SYNC] owner app PIN for test unlock")
            log.append(f"[SYNC] owner password for {email}")
        elif staff_pass:
            user.hashed_password = auth.get_password_hash(staff_pass)
            user.must_change_password = False
            pin = os.getenv("SEED_STAFF_PIN", "1357")
            if not user.hashed_pin:
                user.hashed_pin = auth.get_pin_hash(pin)
                log.append(f"[SYNC] app PIN for {email}")
            log.append(f"[SYNC] password for {email}")
    if log:
        db.commit()
    return log


def _seed_demo_sales_month(db, restaurant, pilau, log: list[str]) -> None:
    """90 days Nairobi-shaped till sales (weekends busier, cash/M-Pesa mix)."""
    from datetime import timedelta

    from time_utils import utcnow

    if pilau is None:
        return
    marker = "[DEMO-SALES-90D]"
    now = utcnow()
    nyama = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.restaurant_id == restaurant.id, models.MenuItem.name.contains("Nyama"))
        .first()
    )
    if nyama is None:
        nyama = models.MenuItem(
            restaurant_id=restaurant.id,
            name="Nyama Choma (demo)",
            price=65000,
            cost_price=22000,
            category="Grill",
        )
        db.add(nyama)
        db.flush()
        log.append("[CREATED] demo dish Nyama Choma")
    for day in range(90):
        when = now - timedelta(days=day)
        exists = (
            db.query(models.Order.id)
            .filter(
                models.Order.restaurant_id == restaurant.id,
                models.Order.notes == f"{marker} day-{day}",
            )
            .first()
        )
        if exists:
            continue
        weekend = when.weekday() >= 4
        qty = (14 if weekend else 8) + (day % 6)
        dish = nyama if day % 3 == 0 else pilau
        unit = dish.price
        line_total = qty * unit
        pay = models.PaymentMethod.MPESA if day % 2 == 0 else models.PaymentMethod.CASH
        otype = models.OrderType.DELIVERY if day % 5 == 0 else models.OrderType.DINE_IN
        hour = 12 + (day % 8) + (2 if weekend else 0)
        stamped = when.replace(hour=min(hour, 22), minute=(day * 7) % 60)
        order = models.Order(
            restaurant_id=restaurant.id,
            status=models.OrderStatus.SERVED,
            order_type=otype,
            is_paid=True,
            payment_method=pay,
            total=line_total,
            notes=f"{marker} day-{day}",
            created_at=stamped,
        )
        db.add(order)
        db.flush()
        db.add(
            models.OrderItem(
                order_id=order.id,
                menu_item_id=dish.id,
                quantity=qty,
                unit_price=unit,
            )
        )
    if not db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.notes == f"{marker} void-sample",
    ).first():
        db.add(
            models.Order(
                restaurant_id=restaurant.id,
                status=models.OrderStatus.CANCELLED,
                order_type=models.OrderType.DINE_IN,
                is_paid=False,
                total=45000,
                notes=f"{marker} void-sample",
                created_at=now - timedelta(days=3),
            )
        )
    created = (
        db.query(models.Order)
        .filter(models.Order.restaurant_id == restaurant.id, models.Order.notes.contains(marker))
        .count()
    )
    if created:
        log.append(f"[REFRESH] demo sales across {created} Nairobi days (90d window)")


def _ensure_empty_wall_no_sales(db, empty_restaurant, log: list[str]) -> None:
    removed = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == empty_restaurant.id,
            models.Order.notes.contains("[DEMO]"),
        )
        .delete(synchronize_session=False)
    )
    if removed:
        log.append(f"[CLEAN] removed {removed} demo orders from empty stack")


def _refresh_demo_feed(db, restaurant, owner, jack, accountant, rice, supplier, pilau, log: list[str]) -> None:
    """Rich [DEMO] rows so owner/jack screens are not empty on backend-test."""
    from datetime import timedelta

    from bill_schedule import business_today
    from time_utils import utcnow

    now = utcnow()
    today = business_today()
    if jack:
        prog = db.query(StaffSetupProgress).filter(StaffSetupProgress.user_id == jack.id).first()
        if prog is None:
            prog = StaffSetupProgress(user_id=jack.id, restaurant_id=restaurant.id)
            db.add(prog)
            db.flush()
        prog.account_completed_at = prog.account_completed_at or now
        prog.recipes_completed_at = prog.recipes_completed_at or now
        prog.updated_at = now
        core_answers = (
            ("ordering_method", "owner_approves", "Owner approves each order"),
            ("receives_deliveries", "yes", "Yes"),
            ("stock_in_pos", "no", "No"),
            ("issues_to_kitchen", "yes", "Yes"),
            ("records_waste", "yes", "Yes"),
            ("closes_the_day", "me", "Jack closes"),
            ("knows_running_costs", "knows_payer", "Knows who pays"),
        )
        for qid, value, label in core_answers:
            if db.query(models.StaffSetupAnswer).filter_by(user_id=jack.id, question_id=qid).first():
                continue
            db.add(
                models.StaffSetupAnswer(
                    user_id=jack.id,
                    restaurant_id=restaurant.id,
                    question_id=qid,
                    value=value,
                    label=label,
                    created_at=now,
                )
            )
        prog.questionnaire_completed_at = now
        restaurant.restock_routing_mode = "owner_approves"
        log.append("[REFRESH] Jack questionnaire complete on data stack")
        if not db.query(models.StaffSetupAnswer).filter(
            models.StaffSetupAnswer.user_id == jack.id,
            models.StaffSetupAnswer.question_id == "receives_deliveries",
            models.StaffSetupAnswer.unlocks == "deliveries",
        ).first():
            db.add(
                models.StaffSetupAnswer(
                    user_id=jack.id,
                    restaurant_id=restaurant.id,
                    question_id="receives_deliveries",
                    value="yes",
                    label="Yes",
                    opens="/store/deliveries",
                    unlocks="deliveries",
                    created_at=now,
                )
            )
            log.append("[REFRESH] deliveries module unlocked for accountant demo")
    if accountant:
        prog = db.query(StaffSetupProgress).filter(StaffSetupProgress.user_id == accountant.id).first()
        if prog:
            prog.account_completed_at = now
            prog.recipes_completed_at = now
            prog.questionnaire_completed_at = now
            prog.updated_at = now

    if not db.query(models.RunningCost).filter(
        models.RunningCost.restaurant_id == restaurant.id,
        models.RunningCost.label.contains("[DEMO]")
    ).first():
        db.add(
            models.RunningCost(
                restaurant_id=restaurant.id,
                user_id=accountant.id if accountant else owner.id,
                kind="rent",
                label="[DEMO] Rent — Westlands",
                amount_cents=8500000,
                status="approved",
                approved_at=now,
                approved_by_user_id=owner.id,
                cadence="monthly",
                due_day=today.day,
                next_due_on=today + timedelta(days=2),
                payment_state="unpaid",
            )
        )
        db.add(
            models.RunningCost(
                restaurant_id=restaurant.id,
                user_id=jack.id if jack else owner.id,
                kind="electricity",
                label="[DEMO] KPLC — amount unknown",
                amount_cents=0,
                status="unknown",
                delegated_to="accountant",
                cadence="monthly",
            )
        )
        log.append("[CREATED] demo bills for Money / approvals")
    else:
        rent = db.query(models.RunningCost).filter(
            models.RunningCost.restaurant_id == restaurant.id,
            models.RunningCost.label.contains("[DEMO] Rent"),
        ).first()
        if rent:
            rent.next_due_on = today + timedelta(days=2)
            rent.payment_state = rent.payment_state or "unpaid"

    import hashlib

    import storage

    if jack and rice:
        chef = db.query(models.StoreChef).filter(models.StoreChef.restaurant_id == restaurant.id).first()
        if chef is None:
            chef = models.StoreChef(
                restaurant_id=restaurant.id,
                name="Chef Mwangi",
                hashed_pin=auth.get_pin_hash("1234"),
                created_by_user_id=jack.id,
            )
            db.add(chef)
            db.flush()
        handover = (
            db.query(models.KitchenHandover)
            .filter(models.KitchenHandover.restaurant_id == restaurant.id)
            .order_by(models.KitchenHandover.id.desc())
            .first()
        )
        if handover is None:
            photo_key = storage.save(
                _DEMO_JPEG,
                key=f"handovers/{restaurant.id}/demo-handover.jpg",
                content_type="image/jpeg",
            )
            handover = models.KitchenHandover(
                restaurant_id=restaurant.id,
                created_by_user_id=jack.id,
                chef_id=chef.id,
                photo_storage_key=photo_key,
                photo_content_type="image/jpeg",
                created_at=now,
                owner_review_status="none",
            )
            db.add(handover)
            db.flush()
            db.add(
                models.KitchenHandoverLine(
                    handover_id=handover.id,
                    inventory_item_id=rice.id,
                    item_name=rice.item_name,
                    quantity=3.5,
                    unit="kg",
                )
            )
            log.append("[CREATED] demo kitchen handover with photo key")
        elif handover.photo_storage_key and not storage.exists(handover.photo_storage_key):
            storage.save(
                _DEMO_JPEG,
                key=handover.photo_storage_key,
                content_type="image/jpeg",
            )
            log.append("[REFRESH] demo handover photo bytes (existing key)")
        if handover and rice:
            demo_out = (
                db.query(models.StockMovement)
                .filter(
                    models.StockMovement.inventory_item_id == rice.id,
                    models.StockMovement.reason.contains("[DEMO] kitchen handover"),
                )
                .first()
            )
            if demo_out is None:
                db.add(
                    models.StockMovement(
                        inventory_item_id=rice.id,
                        movement_type=models.StockMovementType.OUT,
                        quantity=3.5,
                        reason="[DEMO] kitchen handover",
                        performed_by_user_id=jack.id,
                        created_at=now,
                    )
                )
                log.append("[CREATED] demo kitchen OUT movement for custody alerts")

    if pilau:
        pilau.price = 45000
        pilau.cost_price = 14000

    if jack and supplier and rice and not db.query(models.DeliveryReceipt).filter(
        models.DeliveryReceipt.restaurant_id == restaurant.id,
        models.DeliveryReceipt.notes.contains("[DEMO]"),
    ).first():
        receipt = models.DeliveryReceipt(
            restaurant_id=restaurant.id,
            supplier_id=supplier.id,
            received_by_user_id=jack.id,
            received_at=now,
            notes="[DEMO] Fresh Farm delivery — invoice pending prices",
            status="keyed",
        )
        db.add(receipt)
        db.flush()
        for kind in ("invoice", "goods"):
            key = storage.save(_DEMO_JPEG, content_type="image/jpeg")
            db.add(
                models.DeliveryEvidencePhoto(
                    receipt_id=receipt.id,
                    kind=kind,
                    storage_key=key,
                    content_type="image/jpeg",
                    byte_size=len(_DEMO_JPEG),
                    sha256=hashlib.sha256(_DEMO_JPEG).hexdigest(),
                    uploaded_by_user_id=jack.id,
                    uploaded_at=now,
                )
            )
        db.add(
            models.DeliveryReceiptLine(
                receipt_id=receipt.id,
                inventory_item_id=rice.id,
                item_name="[DEMO] Rice",
                quantity=10,
                unit="kg",
                keyed_by_user_id=jack.id,
                keyed_at=now,
            )
        )
        log.append("[CREATED] demo delivery with invoice photo for accountant")

    from services.eleven_v12_seed import seed_v12_catalog

    seeded_pilau = seed_v12_catalog(db, restaurant, jack, log, _DEMO_JPEG)
    if seeded_pilau:
        pilau = seeded_pilau

    members = db.query(models.StaffMember).filter(models.StaffMember.restaurant_id == restaurant.id).all()
    for member in members:
        if db.query(models.LaborShift).filter_by(restaurant_id=restaurant.id, staff_member_id=member.id).first():
            continue
        db.add(
            models.LaborShift(
                restaurant_id=restaurant.id,
                staff_member_id=member.id,
                shift_date=today,
                scheduled_hours=8.0,
                actual_hours=8.0,
                labor_cost=350000,
            )
        )
    if members:
        log.append("[REFRESH] demo labour shifts for P&L pay line")

    import json

    raw = {}
    try:
        raw = json.loads(restaurant.staple_caps_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    block = raw.get("__owner_v11__") if isinstance(raw.get("__owner_v11__"), dict) else {}
    block["reports_past"] = [
        {
            "id": f"daily-{(today - timedelta(days=1)).isoformat()}",
            "kind": "daily",
            "title": f"Daily store report — {(today - timedelta(days=1)).isoformat()}",
            "href": "/eleven/settings/reports",
            "download": "/api/v1/eleven/settings/reports",
        },
        {
            "id": f"daily-{(today - timedelta(days=2)).isoformat()}",
            "kind": "daily",
            "title": f"Daily store report — {(today - timedelta(days=2)).isoformat()}",
            "href": "/eleven/settings/reports",
            "download": "/api/v1/eleven/settings/reports",
        },
        {
            "id": f"weekly-{today.isocalendar().week - 1}",
            "kind": "weekly",
            "title": "Weekly summary — last Monday",
            "href": "/eleven/settings/reports",
            "download": "/api/v1/eleven/settings/reports",
        },
        {
            "id": f"monthly-{today.strftime('%Y-%m')}",
            "kind": "monthly",
            "title": f"Monthly P&L — {today.strftime('%Y-%m')}",
            "href": f"/api/v1/eleven/money/export/monthly/{today.strftime('%Y-%m')}.xlsx",
            "download": f"/api/v1/eleven/money/export/monthly/{today.strftime('%Y-%m')}.xlsx",
        },
    ]
    raw["__owner_v11__"] = block
    restaurant.staple_caps_json = json.dumps(raw)
    log.append("[REFRESH] demo past reports list")

    if rice:
        rice.quantity = min(float(rice.quantity or 0), 1.5)
        rice.low_stock_threshold = max(float(rice.low_stock_threshold or 5), 5)
        log.append("[REFRESH] low stock demo for alerts")

    if jack and supplier and rice:
        po = (
            db.query(models.PurchaseOrder)
            .filter(
                models.PurchaseOrder.restaurant_id == restaurant.id,
                models.PurchaseOrder.notes.contains("[DEMO]"),
            )
            .first()
        )
        if po is None:
            po = models.PurchaseOrder(
                restaurant_id=restaurant.id,
                supplier_id=supplier.id,
                inventory_item_id=rice.id,
                quantity_ordered=8,
                unit="kg",
                cost_per_unit=12000,
                total_cost=96000,
                status="PENDING",
                notes="[DEMO] Auto restock — Rice",
                ordered_at=now,
                requested_by_user_id=jack.id,
            )
            db.add(po)
            log.append("[CREATED] demo pending restock PO")
        elif "[V12-DEMO]" not in (po.notes or ""):
            po.status = "PENDING"
            log.append("[REFRESH] demo restock PO left pending for owner approve")


def provision_test_data_from_env() -> None:
    if not _truthy("SEED_TEST_DATA"):
        return
    owner_first = _truthy("SEED_OWNER_FIRST_LOGIN")
    owner_reset = _truthy("SEED_OWNER_RESET_FIRST_LOGIN")
    password = os.getenv("SEED_OWNER_PASSWORD", "")
    if not owner_first and not password:
        logger.warning(
            "[eleven-seed] SEED_TEST_DATA is set but SEED_OWNER_PASSWORD is missing "
            "(and SEED_OWNER_FIRST_LOGIN is off) — skipped"
        )
        return

    from database import SessionLocal

    db = SessionLocal()
    try:
        for line in ensure_eleven_test_data(
            db,
            password,
            owner_first_login=owner_first,
            owner_reset_first_login=owner_reset,
        ):
            logger.info("[eleven-seed] %s", line)
        sync_flag = os.getenv("SEED_SYNC_TEST_CREDENTIALS", "1").strip().lower()
        if not owner_first and sync_flag in ("1", "true", "yes"):
            for line in sync_test_stack_credentials(db):
                logger.info("[eleven-seed] %s", line)
    except Exception as exc:
        db.rollback()
        logger.warning("[eleven-seed] skipped: %s", exc)
    finally:
        db.close()