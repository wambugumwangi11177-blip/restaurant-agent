from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SqEnum, DateTime, Float, Text, Date, Time, Index, UniqueConstraint, CheckConstraint, text
from sqlalchemy.orm import relationship, declarative_base
import enum
from time_utils import utcnow

Base = declarative_base()

# ──────────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────────
class Role(enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    STAFF = "staff"

class StaffRole(enum.Enum):
    """
    Second, finer-grained axis layered on top of Role — see
    directives/015_staff_roles_permissions.md for the full permission matrix.
    Owner maps 1:1 onto Role.ADMIN (not a parallel concept); this enum only
    exists to subdivide what used to be a single Role.STAFF bucket.
    """
    OWNER = "owner"
    MANAGER = "manager"
    SUPERVISOR = "supervisor"
    CONTROLLER = "controller"
    STOCKKEEPER = "stockkeeper"
    KITCHEN = "kitchen"
    WAITER = "waiter"

class StockTransferStatus(enum.Enum):
    # REQUESTED: kitchen asked for something, no quantity committed yet —
    # the "pull" starting state (directive 017). A store-initiated ("push")
    # transfer skips this and starts at PENDING directly, same as before.
    REQUESTED = "requested"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PREP = "prep"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"

class OrderType(enum.Enum):
    DINE_IN = "dine_in"
    TAKEOUT = "takeout"
    DELIVERY = "delivery"

class TableStatus(enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    CLEANING = "cleaning"

class ReservationStatus(enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"

class StockMovementType(enum.Enum):
    IN = "in"        # Purchase / restock
    OUT = "out"      # Usage / waste
    ADJUST = "adjust" # Manual adjustment

class DeliveryChannel(enum.Enum):
    WALK_IN = "walk_in"
    APP = "app"           # Ordered through customer app
    UBER_EATS = "uber_eats"
    BOLT_FOOD = "bolt_food"
    GLOVO = "glovo"

class PaymentMethod(enum.Enum):
    CASH = "cash"
    MPESA = "mpesa"
    CARD = "card"
    PENDING = "pending"   # Not yet paid

class IncidentType(enum.Enum):
    REMAKE = "remake"
    QUALITY_ISSUE = "quality_issue"
    OTHER = "other"

# ──────────────────────────────────────────────
# TENANT & USER
# ──────────────────────────────────────────────
class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    plan = Column(String, default="free")
    created_at = Column(DateTime, default=utcnow)
    
    users = relationship("User", back_populates="tenant")
    restaurants = relationship("Restaurant", back_populates="tenant")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(SqEnum(Role), default=Role.STAFF)
    failed_login_attempts = Column(Integer, default=0)   # brute-force lockout (2026-07-07 security pass)
    locked_until = Column(DateTime, nullable=True)         # None = not locked
    last_login_at = Column(DateTime, nullable=True)        # set on successful login (staff-activity record)
    # Bumped to invalidate every outstanding JWT for this user (logout-all /
    # credential compromise). Tokens embed the value they were minted with as the
    # "ver" claim; get_current_user rejects a token whose ver != this. Added by
    # migration 017.
    token_version = Column(Integer, default=0, nullable=False)
    # TOTP multi-factor auth (migration 020). mfa_secret is the base32 shared
    # secret (set at /mfa/setup, but MFA only enforced once mfa_enabled flips true
    # after the user proves they can generate a valid code). Nullable so existing
    # users are unaffected until they opt in.
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    # Fine-grained tier layered on top of `role` (directive 015). NULL means
    # "not yet assigned" — deliberately not defaulted, see directive's Edge
    # Cases: guessing a tier for a pre-existing STAFF user could grant access
    # nobody approved. Backfilled to OWNER for existing ADMIN users only.
    staff_role = Column(SqEnum(StaffRole), nullable=True)
    # Account lifecycle (directive 016, added 2026-07-15): StaffMember already
    # had is_active but nothing downstream acted on it — deactivating a roster
    # entry didn't revoke the linked login. Checked in auth.get_current_user
    # alongside token_version, so deactivation takes effect on the very next
    # request rather than just hiding a nav link.
    is_active = Column(Boolean, default=True, nullable=False)
    # Email verification (migration 034). Defaults False for new signups;
    # existing accounts are backfilled True (they were already trusted before
    # this feature existed — retroactively flagging them unverified would just
    # lock real users out of nothing, since nothing currently gates on this
    # flag). Not enforced at login — surfaced to the frontend as a banner
    # (directive: don't lock out staff invited without email access to their
    # own inbox at signup time).
    is_email_verified = Column(Boolean, default=False, nullable=False)
    # Which of the tenant's restaurants this user is currently viewing (audit
    # remediation, Tier 5 item 11 — multi-restaurant switcher). NULL for the
    # overwhelming majority of tenants (single restaurant, nothing to pick)
    # and is the correct default even for a chain until the owner explicitly
    # switches — deps.py's get_or_create_restaurant falls back to the
    # tenant's first restaurant when this is unset or points at a restaurant
    # outside the user's own tenant, exactly matching pre-existing behavior.
    # No ondelete cascade: if the selected restaurant is ever removed, the
    # user simply falls back to that same default next request rather than
    # erroring — see deps.py.
    active_restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True)

    tenant = relationship("Tenant", back_populates="users")

# ──────────────────────────────────────────────
# RESTAURANT & TABLES
# ──────────────────────────────────────────────
class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    name = Column(String)
    address = Column(String)
    owner_phone = Column(String, nullable=True)   # WhatsApp owner routing (was OWNER_PHONE_{id} env var)
    # Preferred channel for owner alerts: "whatsapp" (default), "sms", or "both".
    # SMS matters in Kenya where not every owner uses WhatsApp.
    owner_channel = Column(String, default="whatsapp")
    # Enterprise hierarchy (Phase 10). Nullable + backward-compatible: a single
    # independent restaurant leaves both null and behaves exactly as before; a
    # chain groups its sites under an Organization and (optionally) a Region.
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    region_id       = Column(Integer, ForeignKey("regions.id"), nullable=True, index=True)
    # GPS staff check-in (migration 037). Nullable — until an owner sets these
    # (via PUT /restaurant), GPS check-in proximity checks are simply skipped
    # rather than guessed at (same "don't guess" posture as par_level/
    # default_supplier_id in directive 018).
    latitude        = Column(Float, nullable=True)
    longitude       = Column(Float, nullable=True)

    tenant = relationship("Tenant", back_populates="restaurants")
    menu_items = relationship("MenuItem", back_populates="restaurant")
    orders = relationship("Order", back_populates="restaurant")
    inventory_items = relationship("InventoryItem", back_populates="restaurant")
    tables = relationship("Table", back_populates="restaurant")
    reservations = relationship("Reservation", back_populates="restaurant")

class Table(Base):
    """Physical tables in the restaurant — required for reservation intelligence."""
    __tablename__ = "tables"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)
    table_number = Column(Integer)
    capacity = Column(Integer, default=4)
    status = Column(SqEnum(TableStatus), default=TableStatus.AVAILABLE)

    restaurant = relationship("Restaurant", back_populates="tables")
    reservations = relationship("Reservation", back_populates="table")
    __table_args__ = (
        # A table number is unique within a restaurant — two "Table 5"s in the
        # same venue is a data error (and would confuse reservation seating).
        UniqueConstraint("restaurant_id", "table_number", name="uq_tables_restaurant_number"),
    )

# ──────────────────────────────────────────────
# MENU ITEMS (Enhanced for AI)
# ──────────────────────────────────────────────
class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)
    name = Column(String)
    description = Column(Text, default="")
    price = Column(Integer)           # Sale price in cents
    cost_price = Column(Integer, default=0)  # Cost price in cents — for margin analysis
    category = Column(String)
    image_url = Column(String, default="")
    is_available = Column(Boolean, default=True)
    prep_station = Column(String, default="main")  # grill, fryer, salad, drinks, main
    avg_prep_minutes = Column(Float, default=10.0)   # Baseline prep time
    
    restaurant = relationship("Restaurant", back_populates="menu_items")
    # passive_deletes=True: without it, SQLAlchemy's unit-of-work proactively
    # NULLs order_items.menu_item_id on a MenuItem delete (since it's a plain
    # relationship with no cascade config) BEFORE the DELETE reaches the DB —
    # silently defeating the ON DELETE RESTRICT from migration 028. This tells
    # the ORM to leave child rows alone and let the DB constraint be
    # authoritative. Caught by tests/test_fk_ondelete.py.
    order_items = relationship("OrderItem", back_populates="menu_item", passive_deletes=True)
    __table_args__ = (
        # Sale and cost prices are money in cents — never negative (0 allowed).
        CheckConstraint("price >= 0", name="ck_menu_items_price_nonneg"),
        CheckConstraint("cost_price >= 0", name="ck_menu_items_cost_nonneg"),
    )

# ──────────────────────────────────────────────
# ORDERS (Enhanced for AI)
# ──────────────────────────────────────────────
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    status = Column(SqEnum(OrderStatus), default=OrderStatus.PENDING)
    order_type = Column(SqEnum(OrderType), default=OrderType.DINE_IN)
    delivery_channel = Column(SqEnum(DeliveryChannel), default=DeliveryChannel.WALK_IN)
    payment_method = Column(SqEnum(PaymentMethod), default=PaymentMethod.PENDING)
    is_paid = Column(Boolean, default=False)
    mpesa_checkout_request_id = Column(String, unique=True, nullable=True)
    mpesa_receipt = Column(String, nullable=True)
    table_number = Column(Integer, nullable=True)
    customer_name = Column(String, default="")
    customer_phone = Column(String, default="")
    total = Column(Integer)  # In cents
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    restaurant = relationship("Restaurant", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    __table_args__ = (
        # Tenant-scoped list/ordering and status filtering are the hot read paths;
        # customer_phone drives export/erasure/customer resolution. FK columns
        # aren't auto-indexed on Postgres — see migration 015.
        Index("ix_orders_restaurant_created", "restaurant_id", "created_at"),
        Index("ix_orders_restaurant_status", "restaurant_id", "status"),
        Index("ix_orders_customer_phone", "customer_phone"),
        # An order total is money in cents — never negative. Allows 0 (comped/
        # zero-total orders are legitimate). See migration 016.
        CheckConstraint("total >= 0", name="ck_orders_total_nonneg"),
        # A real M-Pesa receipt number is unique across all orders — two orders
        # can never legitimately settle against the same Safaricom transaction.
        # Partial (WHERE NOT NULL) so unpaid orders (mpesa_receipt IS NULL)
        # never collide. See migration 029.
        Index(
            "uq_orders_mpesa_receipt", "mpesa_receipt", unique=True,
            postgresql_where=text("mpesa_receipt IS NOT NULL"),
            sqlite_where=text("mpesa_receipt IS NOT NULL"),
        ),
    )


class OrderAuditAction(enum.Enum):
    VOID = "void"
    CANCEL = "cancel"
    REFUND = "refund"
    PAYMENT_CHANGE = "payment_change"


class OrderAudit(Base):
    """
    Who did what to an order and when — persisted actor trail for status/payment
    changes. Previously this only existed transiently as `actor_user_id` on the
    event-bus payload (events/bus.py EventType.ORDER_CANCELLED etc.), never
    written to a row, which made void/refund pattern detection (fraud) impossible.
    This table is the source of truth for that; fraud detection (ai/fraud/) reads
    from it directly rather than replaying the event bus.
    """
    __tablename__ = "order_audits"

    id             = Column(Integer, primary_key=True, index=True)
    order_id       = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    restaurant_id  = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    action         = Column(SqEnum(OrderAuditAction), nullable=False)
    actor_user_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason         = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=utcnow)

    order      = relationship("Order")
    restaurant = relationship("Restaurant")
    actor      = relationship("User")

    __table_args__ = (
        # Fraud detection's hot path is "this staff member's actions in a
        # window" and "this order's history" — both need their own index,
        # a composite on (actor, created_at) doesn't serve the order_id lookup.
        Index("ix_order_audits_restaurant_actor_created", "restaurant_id", "actor_user_id", "created_at"),
        Index("ix_order_audits_order", "order_id"),
    )


class OrderItem(Base):
    """Links orders to menu items — critical for menu performance analysis."""
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    # CASCADE: a line item has no independent value once its order is gone
    # (matches the existing ORM cascade="all, delete-orphan" on Order.items,
    # now also enforced at the DB level — see migration 028).
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    # RESTRICT (explicit): order history/pricing is an audit trail that must
    # survive a menu item being edited away — see migration 028.
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="RESTRICT"), index=True)
    quantity = Column(Integer, default=1)
    unit_price = Column(Integer)  # Snapshot of price at time of order
    
    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")
    prep_time = relationship("PrepTime", back_populates="order_item", uselist=False)
    __table_args__ = (
        # You cannot order a non-positive quantity; a line's unit price is money.
        CheckConstraint("quantity > 0", name="ck_order_items_qty_pos"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_price_nonneg"),
    )

# ──────────────────────────────────────────────
# KDS: PREP TIME TRACKING
# ──────────────────────────────────────────────
class PrepTime(Base):
    """Tracks actual kitchen prep time per order item — powers KDS intelligence."""
    __tablename__ = "prep_times"
    id = Column(Integer, primary_key=True, index=True)
    # CASCADE: 1:1 owned child of the order item — see migration 028.
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="CASCADE"), index=True)
    station = Column(String, default="main")  # grill, fryer, salad, drinks, main
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    actual_minutes = Column(Float, nullable=True)

    order_item = relationship("OrderItem", back_populates="prep_time")


class KitchenIncident(Base):
    """
    A remake or quality issue logged against an order (migration 037) —
    previously nowhere to record either, per the owner's walkthrough notes:
    "if there's any food that needs to be remade, it's also put in the
    system manually" / "if any issue happens in the kitchen, it's put in."
    order_item_id is nullable: some issues are order-level (wrong table),
    not tied to one line item.
    """
    __tablename__ = "kitchen_incidents"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=True)
    incident_type = Column(SqEnum(IncidentType), nullable=False)
    reason = Column(Text, default="")
    reported_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")
    order = relationship("Order")
    order_item = relationship("OrderItem")

    __table_args__ = (
        Index("ix_kitchen_incidents_restaurant_created", "restaurant_id", "created_at"),
    )

# ──────────────────────────────────────────────
# INVENTORY (Enhanced for AI)
# ──────────────────────────────────────────────
class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)
    item_name = Column(String)
    quantity = Column(Float, default=0)
    unit = Column(String)
    # Stored as integer cents (migration 035 — was a Float storing whole KES,
    # the one money column in this schema not in cents like PurchaseOrder's).
    # Exposed as `cost_per_unit` (KES) via the property below so every
    # existing consumer — schemas.py, routers/inventory.py, ai/reorder.py,
    # ai/inventory_predictor.py, the frontend's `KES {cost_per_unit}` display —
    # keeps reading/writing plain KES floats unchanged.
    cost_per_unit_cents = Column(Integer, default=0)
    low_stock_threshold = Column(Integer)
    expiry_days = Column(Integer, default=30)  # Avg shelf life — for spoilage prediction
    # When the owner was last WhatsApped that this item is low/out. The stock
    # check runs every 2h; without this a persistently low item re-alerts every
    # cycle (7 messages/day, per item) until someone restocks. See
    # ai/whatsapp/brain.STOCK_ALERT_COOLDOWN_HOURS. Added by migration 010.
    last_alerted_at = Column(DateTime, nullable=True)
    # Par-level reordering (directive 018). `low_stock_threshold` above
    # already IS the reorder point in every alert path that reads it
    # (get_critical_stock_alerts, run_stock_check) — this doesn't duplicate
    # it, par_level is the NEW piece: how much to restock UP TO once that
    # point is crossed. Nullable — an item with no par_level set is simply
    # never auto-drafted, not defaulted to a guessed number.
    par_level          = Column(Float, nullable=True)
    default_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    restaurant = relationship("Restaurant", back_populates="inventory_items")
    # passive_deletes=True: same reasoning as MenuItem.order_items above — let
    # the DB's ON DELETE RESTRICT (migration 028) be authoritative instead of
    # the ORM proactively nulling stock_movements.inventory_item_id.
    movements = relationship("StockMovement", back_populates="inventory_item", passive_deletes=True)
    default_supplier = relationship("Supplier", foreign_keys=[default_supplier_id])

    @property
    def cost_per_unit(self) -> float:
        """KES, computed from cost_per_unit_cents. Not SQL-queryable (a plain
        Python property, not a hybrid_property) — verified nothing in this
        codebase filters/orders/aggregates on InventoryItem.cost_per_unit at
        the query level, only plain attribute access."""
        return (self.cost_per_unit_cents or 0) / 100

    @cost_per_unit.setter
    def cost_per_unit(self, kes_value) -> None:
        self.cost_per_unit_cents = round((kes_value or 0) * 100)

class StockMovement(Base):
    """Tracks inventory in/out — powers depletion prediction and reorder intelligence."""
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    # RESTRICT (explicit): this is the theft/shrinkage audit trail — it must
    # survive an inventory item being deleted — see migration 028.
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True)
    movement_type = Column(SqEnum(StockMovementType))
    quantity = Column(Float)
    reason = Column(String, default="")  # "sale", "waste", "purchase", "adjustment"
    created_at = Column(DateTime, default=utcnow)
    # Chain-of-custody (directive 016). Nullable: historical rows have no
    # actor and can't be backfilled honestly — don't guess one. Every write
    # path in routers/inventory.py and routers/stock_custody.py stamps this
    # going forward.
    performed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    inventory_item = relationship("InventoryItem", back_populates="movements")
    performed_by = relationship("User")

# ──────────────────────────────────────────────
# RESERVATIONS (New for AI)
# ──────────────────────────────────────────────
class Reservation(Base):
    """Reservation system — powers no-show prediction and revenue-per-seat optimization."""
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=True, index=True)
    customer_name = Column(String)
    customer_phone = Column(String, default="")
    customer_email = Column(String, default="")
    party_size = Column(Integer, default=2)
    reservation_date = Column(Date)
    reservation_time = Column(Time)
    duration_minutes = Column(Integer, default=90)
    status = Column(SqEnum(ReservationStatus), default=ReservationStatus.CONFIRMED)
    deposit_paid = Column(Boolean, default=False)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    # When a same-day reminder was last sent — prevents a scheduler misfire/restart
    # from re-sending. See ai/whatsapp/brain.run_reservation_reminders.
    reminder_sent_at = Column(DateTime, nullable=True)

    restaurant = relationship("Restaurant", back_populates="reservations")
    table = relationship("Table", back_populates="reservations")
    __table_args__ = (
        # Availability/day queries filter by restaurant + date; customer_phone
        # drives export/erasure. See migration 015.
        Index("ix_reservations_restaurant_date", "restaurant_id", "reservation_date"),
        Index("ix_reservations_customer_phone", "customer_phone"),
        # A booking is for at least one guest.
        CheckConstraint("party_size > 0", name="ck_reservations_party_pos"),
    )

# ─────────────────────────────────────────────────────────────────────────────
# EXISTING (from previous release) — keep as-is
# ─────────────────────────────────────────────────────────────────────────────

class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"
    id                      = Column(Integer, primary_key=True, index=True)
    restaurant_id           = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    # CASCADE: an AI suggestion artifact tied 1:1 to the item — see migration 028.
    menu_item_id            = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    recommendation_type     = Column(String, nullable=False)
    current_price           = Column(Integer, nullable=False)
    suggested_price         = Column(Integer, nullable=False)
    reason                  = Column(Text, default="")
    when_to_apply           = Column(String, default="All times")
    monthly_impact_cents    = Column(Integer, default=0)
    recommendation_strength = Column(Integer, default=0)
    status                  = Column(String, default="PENDING")
    rejection_reason        = Column(String, default="")
    created_at              = Column(DateTime, default=utcnow)
    actioned_at             = Column(DateTime, nullable=True)
    menu_item  = relationship("MenuItem")
    restaurant = relationship("Restaurant")
    __table_args__ = (
        Index("ix_pricing_rec_restaurant_status", "restaurant_id", "status"),
        Index("ix_pricing_rec_item_status", "menu_item_id", "status"),
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    recipient     = Column(String, nullable=False)
    message_body  = Column(Text, nullable=False)
    message_type  = Column(String, nullable=False)
    status        = Column(String, nullable=False)
    twilio_sid    = Column(String, default="")
    llm_model     = Column(String, nullable=True)
    input_tokens  = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at    = Column(DateTime, default=utcnow)
    restaurant    = relationship("Restaurant")
    __table_args__ = (
        Index("ix_agent_messages_restaurant_created", "restaurant_id", "created_at"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2: AGENT MEMORY SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class MemoryEvent(Base):
    """
    Structured long-term memory for the AI agents.
    Stores events that affect demand patterns — the system learns from these
    when making future recommendations.

    Examples:
      - Nairobi Marathon caused -40% foot traffic, +80% delivery orders
      - Mother's Day 2024: +120% revenue, ran out of chicken
      - Ramadan 2024: dinner service shifted to 8pm-11pm

    The agent retrieves relevant memories by event_type + month, not by
    semantic similarity (that's Phase 2 with a vector DB).
    """
    __tablename__ = "memory_events"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    event_type    = Column(String, nullable=False)   # holiday, promotion, stockout, weather, competitor, local_event
    event_name    = Column(String, nullable=False)   # "Mother's Day 2024", "Ramadan 2024", "Heavy rain 2024-03-15"
    event_date    = Column(Date, nullable=False)
    month_number  = Column(Integer, nullable=False)  # 1-12, for seasonal retrieval
    day_of_week   = Column(Integer, nullable=True)   # 0=Mon, for DOW retrieval
    impact_type   = Column(String, nullable=False)   # traffic_spike, traffic_drop, demand_shift, stockout, price_change
    revenue_delta_pct   = Column(Float, nullable=True)   # +120.0 = 120% above normal
    traffic_delta_pct   = Column(Float, nullable=True)
    affected_items      = Column(Text, default="")   # JSON list of item names affected
    agent_notes         = Column(Text, default="")   # What the agent learned
    human_notes         = Column(Text, default="")   # Owner annotation
    created_at          = Column(DateTime, default=utcnow)
    created_by          = Column(String, default="system")   # "system" or user email

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_memory_events_restaurant_month", "restaurant_id", "month_number"),
        Index("ix_memory_events_restaurant_type",  "restaurant_id", "event_type"),
    )


class ConversationTurn(Base):
    """
    Short-term conversation memory for the WhatsApp LLM orchestrator (Phase 6).
    Persists each owner<->assistant turn so a follow-up ("and last week?") has
    context the current stateless-per-message path lacks.

    Keyed by restaurant_id ALONE, deliberately: the owner is the only free-form
    LLM user per restaurant (customers use the deterministic keyword path in
    brain.handle_customer_message, which never reaches the LLM), so no per-sender
    threading is needed. Gated behind FEATURE_CONVERSATION_MEMORY (default off);
    nothing reads/writes this table until the flag is enabled.
    """
    __tablename__ = "conversation_turns"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    role          = Column(String, nullable=False)   # "user" | "assistant"
    content       = Column(Text, nullable=False)
    created_at    = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_conversation_turns_restaurant_created", "restaurant_id", "created_at"),
    )


class ProductEvent(Base):
    """
    Product-analytics events for the APP's own users (owners/staff) — feature
    usage, funnels, retention — as distinct from the restaurant's business
    metrics. Self-hosted (no PostHog/third party): a row per tracked action,
    queryable for counts/DAU/funnel. Phase 8.
    """
    __tablename__ = "product_events"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_name  = Column(String, nullable=False)   # e.g. "viewed_dashboard", "approved_pricing"
    properties  = Column(Text, default="")          # JSON blob of event context
    created_at  = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_product_events_tenant_name_created", "tenant_id", "event_name", "created_at"),
    )


class Subscription(Base):
    """
    Per-tenant subscription/billing state (Phase 10). The plan/status state machine
    is provider-agnostic; `provider` records HOW it's billed ("manual" by default —
    the actual payment integration, e.g. M-Pesa recurring or Stripe, is a pluggable
    business decision, so this stores the state without hard-wiring a processor).
    """
    __tablename__ = "subscriptions"

    id                 = Column(Integer, primary_key=True, index=True)
    tenant_id          = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False)
    plan               = Column(String, nullable=False, default="free")     # free | pro | enterprise
    status             = Column(String, nullable=False, default="active")   # active | past_due | canceled
    provider           = Column(String, nullable=False, default="manual")   # manual | mpesa | stripe
    current_period_end = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=utcnow)
    updated_at         = Column(DateTime, default=utcnow, onupdate=utcnow)

    tenant = relationship("Tenant")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3: KNOWLEDGE GRAPH — INGREDIENT TO MENU ITEM MAPPING
# ─────────────────────────────────────────────────────────────────────────────

class MenuIngredient(Base):
    """
    Links inventory items (ingredients) to menu items.
    Enables: "If chicken stock hits 0, which menu items are affected?"
    The orchestrator uses this for cascade impact analysis.

    quantity_per_serving: how many units of the ingredient per 1 serving.
    unit matches the InventoryItem.unit for that ingredient.
    """
    __tablename__ = "menu_ingredients"

    id                  = Column(Integer, primary_key=True, index=True)
    # CASCADE: a recipe link is meaningless once either side no longer exists —
    # see migration 028.
    menu_item_id        = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id   = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    quantity_per_serving = Column(Float, nullable=False, default=1.0)
    is_critical         = Column(Boolean, default=True)   # False = garnish, can be skipped

    menu_item       = relationship("MenuItem")
    inventory_item  = relationship("InventoryItem")

    __table_args__ = (
        UniqueConstraint("menu_item_id", "inventory_item_id", name="uq_menu_ingredient"),
        Index("ix_menu_ingredients_inventory", "inventory_item_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4: LABOR INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

class StaffMember(Base):
    """Staff roster — linked to User for those with system access, standalone for those without."""
    __tablename__ = "staff_members"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)   # Optional
    name          = Column(String, nullable=False)
    role_title    = Column(String, default="")   # "Head Chef", "Waiter", "Cashier"
    hourly_rate   = Column(Integer, default=0)   # In cents
    # E.164 phone (directive 016). Nullable — many roster entries (see
    # user_id above) have no way to reach them electronically at all. Lets a
    # staff member with no dashboard login still receive/confirm a stock
    # transfer over WhatsApp/SMS (routers/webhooks.py staff resolution).
    phone         = Column(String, nullable=True)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")
    shifts     = relationship("LaborShift", back_populates="staff_member")

    __table_args__ = (
        Index("ix_staff_members_restaurant", "restaurant_id"),
        # Two roster entries at the same restaurant sharing a phone number is a
        # data error (webhooks.py resolves an inbound WhatsApp/SMS sender to a
        # staff member by phone — a duplicate makes that resolution ambiguous).
        # Partial (WHERE phone IS NOT NULL): phone is optional (see comment
        # above), so multiple NULLs must not collide. See migration 030.
        Index(
            "uq_staff_members_restaurant_phone", "restaurant_id", "phone", unique=True,
            postgresql_where=text("phone IS NOT NULL"),
            sqlite_where=text("phone IS NOT NULL"),
        ),
    )


class ImpersonationSession(Base):
    """
    Live/historical record of an Owner "view as" session (real impersonation,
    not a UI-only preview — see the staff-roles-permissions skill). A row is
    the sole source of truth for whether an impersonation token is still
    valid: JWTs alone can't support "end this session right now" without also
    bumping the target's token_version, which would kick the target out of
    their OWN concurrent session too — wrong. get_current_user checks this
    table (via the token's imp_session_id claim) on every request.
    """
    __tablename__ = "impersonation_sessions"

    id                    = Column(Integer, primary_key=True, index=True)
    tenant_id             = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    restaurant_id         = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    impersonator_user_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at            = Column(DateTime, default=utcnow)
    expires_at            = Column(DateTime, nullable=False)
    ended_at              = Column(DateTime, nullable=True)
    # "manual" (Owner clicked End) | "target_revoked" | null while active.
    end_reason            = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_impersonation_sessions_target", "target_user_id"),
        Index("ix_impersonation_sessions_impersonator", "impersonator_user_id"),
    )


class AuthTokenPurpose(enum.Enum):
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFY = "email_verify"


class AuthToken(Base):
    """
    Single-use, short-lived tokens backing password reset and email
    verification (migration 034). Stores a SHA-256 hash of the token, never
    the raw value — same "don't store the secret itself" principle as
    hashed_password, so a DB read (backup leak, SQLi) can't be replayed as a
    valid reset/verify link. The raw token only ever exists in the emailed
    link and the requester's memory of it.
    """
    __tablename__ = "auth_tokens"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash  = Column(String, nullable=False, index=True)
    purpose     = Column(SqEnum(AuthTokenPurpose), nullable=False)
    expires_at  = Column(DateTime, nullable=False)
    used_at     = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=utcnow)

    user = relationship("User")


class LaborShift(Base):
    """
    Tracks every staff shift — clock in/out.
    Powers: labor cost %, sales per employee, productivity analysis.
    """
    __tablename__ = "labor_shifts"

    id              = Column(Integer, primary_key=True, index=True)
    restaurant_id   = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    staff_member_id = Column(Integer, ForeignKey("staff_members.id"), nullable=False)
    shift_date      = Column(Date, nullable=False)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end   = Column(DateTime, nullable=True)
    actual_start    = Column(DateTime, nullable=True)    # Clock-in
    actual_end      = Column(DateTime, nullable=True)    # Clock-out
    scheduled_hours = Column(Float, nullable=True)
    actual_hours    = Column(Float, nullable=True)
    labor_cost      = Column(Integer, nullable=True)    # Computed: hours * hourly_rate (cents)
    notes           = Column(Text, default="")
    created_at      = Column(DateTime, default=utcnow)
    # GPS check-in (migration 037). Captured whenever the clocking-in device
    # shares its location; nullable because it's opt-in (a device that denies
    # location permission can still clock in). Distance-from-restaurant is
    # only ever checked, never blocking — see routers/attendance.py — because
    # Restaurant.latitude/longitude are themselves optional (an owner who
    # hasn't set them yet gets no flag, not a false one).
    clock_in_lat    = Column(Float, nullable=True)
    clock_in_lng    = Column(Float, nullable=True)
    clock_out_lat   = Column(Float, nullable=True)
    clock_out_lng   = Column(Float, nullable=True)
    # Set true when clock_in_lat/lng was farther than the proximity threshold
    # from the restaurant's own coordinates — a visibility flag for managers,
    # never a block on clocking in (see routers/attendance.py).
    clock_in_flagged = Column(Boolean, default=False, nullable=False)

    staff_member = relationship("StaffMember", back_populates="shifts")
    restaurant   = relationship("Restaurant")

    __table_args__ = (
        Index("ix_labor_shifts_restaurant_date", "restaurant_id", "shift_date"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4B: STAFF NOTIFICATIONS + SUPPORT
#
# The Twilio/WhatsApp channel (ai/whatsapp) requires a funded Twilio account
# and, until directive 016's staff-comms follow-up, only ever reached the
# restaurant owner's phone — no staff member ever got an alert. This layer is
# a channel that costs nothing and needs no external account: an in-app feed
# (Notification, always populated) plus optional Web Push (PushSubscription,
# best-effort — see ai/notify.py). See ai/orchestrator/push_notifier.py for
# the event-bus subscriber that populates Notification rows, and
# routers/support.py for the staff support-ticket system that also notifies
# through this same channel.
# ─────────────────────────────────────────────────────────────────────────────

class Notification(Base):
    """
    A persisted in-app notification for one dashboard user. Always written
    regardless of whether that user has an active PushSubscription — the
    in-app feed (routers/notifications.py GET /) must never depend on push
    having been set up, since push is inherently best-effort (browser
    permission can be denied, iOS requires the PWA be installed, etc).
    """
    __tablename__ = "notifications"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title      = Column(String, nullable=False)
    body       = Column(Text, nullable=False)
    # Raw EventType.value string (e.g. "stock.critical"), not a DB enum — so
    # the event registry can grow without a migration. "support.ticket" /
    # "support.reply" for support-ticket notifications, which don't go
    # through events/bus.py at all (see routers/support.py).
    event_type = Column(String, nullable=False)
    url        = Column(String, nullable=True)   # deep link, e.g. /dashboard/inventory
    is_read    = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    # Escalation engine fields (ai/escalation/engine.py). severity/escalation_level
    # default to the "no escalation" case so every pre-existing notify_users() call
    # site keeps working unchanged — only events routed through escalate() opt in.
    # is_read (above) is a UI concept ("have I seen this"); acknowledged_at is a
    # distinct escalation concept ("has a human confirmed they're handling this") —
    # a manager can read a critical alert without acknowledging it, and the
    # escalation clock only cares about the latter.
    severity          = Column(String, nullable=True)   # "critical" | "high" | "medium" | None
    acknowledged_at   = Column(DateTime, nullable=True)
    escalation_level  = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "is_read"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # Escalation job's hot query: unacknowledged severe notifications past a
        # timeout, scanned every 5 min — needs its own index, not covered by the
        # two above (neither includes severity or acknowledged_at).
        Index("ix_notifications_escalation_scan", "severity", "acknowledged_at"),
    )


class PushSubscription(Base):
    """
    One browser/device's Web Push subscription (VAPID). `endpoint` is unique
    per browser+origin regardless of which user is logged in when it
    subscribes — see routers/notifications.py's upsert-by-endpoint logic for
    why user_id can legitimately be reassigned on an existing row (a
    different staff member logging into the same shared device/tablet).
    """
    __tablename__ = "push_subscriptions"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    endpoint   = Column(String, nullable=False, unique=True)
    p256dh     = Column(String, nullable=False)
    auth       = Column(String, nullable=False)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_push_subscriptions_user", "user_id"),
    )


class SupportTicketStatus(enum.Enum):
    OPEN        = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED    = "resolved"
    CLOSED      = "closed"


class SupportTicket(Base):
    """
    An in-app support ticket, replacing "call/WhatsApp the owner" as the way
    staff raise an issue while Twilio is unfunded. Any authenticated
    dashboard user can open one; OWNER/MANAGER-tier users can see and
    triage every ticket at their restaurant (routers/support.py).
    """
    __tablename__ = "support_tickets"

    id             = Column(Integer, primary_key=True, index=True)
    restaurant_id  = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    created_by_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject        = Column(String, nullable=False)
    status         = Column(SqEnum(SupportTicketStatus), default=SupportTicketStatus.OPEN, nullable=False)
    created_at     = Column(DateTime, default=utcnow)
    updated_at     = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")
    messages   = relationship(
        "SupportTicketMessage", back_populates="ticket",
        order_by="SupportTicketMessage.created_at", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_support_tickets_restaurant_status", "restaurant_id", "status"),
    )


class SupportTicketMessage(Base):
    """One message in a support ticket's thread — the opening message and
    every reply are both rows here, so the thread has a single shape."""
    __tablename__ = "support_ticket_messages"

    id         = Column(Integer, primary_key=True, index=True)
    ticket_id  = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False)
    sender_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    body       = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    ticket = relationship("SupportTicket", back_populates="messages")

    __table_args__ = (
        Index("ix_support_ticket_messages_ticket", "ticket_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 5: SUPPLY CHAIN INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

class Supplier(Base):
    """Supplier master — tracks who supplies what."""
    __tablename__ = "suppliers"

    id                = Column(Integer, primary_key=True, index=True)
    restaurant_id     = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    name              = Column(String, nullable=False)
    contact_phone     = Column(String, default="")
    contact_email     = Column(String, default="")
    avg_lead_days     = Column(Float, default=1.0)    # Avg days from order to delivery
    reliability_score = Column(Float, default=100.0)  # 0-100, computed from history
    # Tiered PO auto-approval override (ai/workflows/engine.py). NULL (default)
    # means "derive trust from reliability_score >= AUTO_APPROVE_RELIABILITY_MIN"
    # (see ai/reorder.py). True/False is an explicit owner override that always
    # wins over the score — e.g. a brand-new high-score supplier the owner
    # doesn't yet trust, or a long-standing supplier the owner has vetted below
    # the auto threshold.
    requires_approval = Column(Boolean, nullable=True)
    is_active         = Column(Boolean, default=True)
    notes             = Column(Text, default="")
    created_at        = Column(DateTime, default=utcnow)

    restaurant     = relationship("Restaurant")
    # passive_deletes=True: same reasoning as MenuItem.order_items above. Was
    # "working" only by coincidence (purchase_orders.supplier_id is NOT NULL,
    # so the ORM's phantom nulling UPDATE happened to fail too) — this makes
    # the DB's ON DELETE RESTRICT (migration 028) the real, intended reason.
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier", passive_deletes=True)

    __table_args__ = (
        Index("ix_suppliers_restaurant", "restaurant_id"),
    )


class PurchaseOrder(Base):
    """
    Records purchase orders to suppliers.
    Powers: lead time analysis, reliability scoring, cost tracking.
    Status: PENDING → SENT → DELIVERED (or LATE / PARTIAL)
    """
    __tablename__ = "purchase_orders"

    id                = Column(Integer, primary_key=True, index=True)
    restaurant_id     = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    # RESTRICT (explicit): procurement/financial history — see migration 028.
    supplier_id       = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    # SET NULL: already nullable — keep the purchase record even if the catalog
    # item it referred to is later removed — see migration 028.
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    quantity_ordered  = Column(Float, nullable=False)
    quantity_received = Column(Float, nullable=True)
    unit              = Column(String, default="")
    cost_per_unit     = Column(Integer, default=0)   # Cents
    total_cost        = Column(Integer, default=0)   # Cents
    status            = Column(String, default="PENDING")   # PENDING, SENT, DELIVERED, LATE, PARTIAL
    ordered_at        = Column(DateTime, default=utcnow)
    expected_at       = Column(DateTime, nullable=True)
    delivered_at      = Column(DateTime, nullable=True)
    notes             = Column(Text, default="")

    supplier       = relationship("Supplier", back_populates="purchase_orders")
    inventory_item = relationship("InventoryItem")
    restaurant     = relationship("Restaurant")

    __table_args__ = (
        Index("ix_purchase_orders_restaurant_status", "restaurant_id", "status"),
        Index("ix_purchase_orders_supplier", "supplier_id"),
    )


class StockTransfer(Base):
    """
    Store→kitchen leg of the chain of custody (directive 016). Deliberately a
    two-party record, not a single StockMovement row: the sender declares a
    quantity, the receiver independently confirms what actually arrived. A
    mismatch (confirmed_quantity != quantity) is the theft/loss signal — it
    only exists because both sides report independently, so trust isn't
    self-certified by whichever party benefits from under-reporting.

    On a matching confirm, this also writes the underlying StockMovement
    OUT/IN pair so existing depletion-prediction code (which reads
    StockMovement, not this table) keeps working unmodified.
    """
    __tablename__ = "stock_transfers"

    id                    = Column(Integer, primary_key=True, index=True)
    restaurant_id         = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    # RESTRICT (explicit): a chain-of-custody record — see migration 028.
    inventory_item_id     = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    # Nullable (directive 017): a REQUESTED (pull) transfer has no committed
    # quantity yet — the kitchen is asking, not declaring. Set when fulfilled.
    quantity              = Column(Float, nullable=True)   # What the sender declares
    unit                  = Column(String, default="")
    from_location         = Column(String, default="store")     # "store", "kitchen"
    to_location            = Column(String, default="kitchen")
    status                = Column(SqEnum(StockTransferStatus), default=StockTransferStatus.PENDING)
    # Kitchen-initiated ("pull") requests only — null for the original
    # store-initiated ("push") flow. See directive 017.
    requested_by_user_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    requested_at          = Column(DateTime, nullable=True)
    # "Who declared the quantity being sent." Set immediately for a push
    # transfer; set at fulfil-time (REQUESTED -> PENDING) for a pull one —
    # hence nullable now, where it used to be required at creation.
    initiated_by_user_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    initiated_at          = Column(DateTime, nullable=True)
    confirmed_by_user_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at          = Column(DateTime, nullable=True)
    confirmed_quantity    = Column(Float, nullable=True)   # What the receiver actually counted
    notes                 = Column(Text, default="")

    restaurant      = relationship("Restaurant")
    inventory_item  = relationship("InventoryItem")
    requested_by    = relationship("User", foreign_keys=[requested_by_user_id])
    initiated_by    = relationship("User", foreign_keys=[initiated_by_user_id])
    confirmed_by    = relationship("User", foreign_keys=[confirmed_by_user_id])

    __table_args__ = (
        Index("ix_stock_transfers_restaurant_status", "restaurant_id", "status"),
    )


class StockCount(Base):
    """
    Physical stock count (directive 017) — the independent check that keeps
    theft/shrinkage detection real once ingredient deduction is automatic.

    Once StockMovement OUT entries are written automatically from recipes
    (directive 017's order-time auto-deduction), comparing "theoretical
    usage" against "recorded StockMovement OUT" stops being a real signal —
    the recorded movements ARE the recipe math, so they always agree with
    themselves. A physical count is the one number in this system that comes
    from someone actually looking at the shelf, independent of anything the
    system already believes — which is what makes a mismatch here meaningful.

    Submitting a count also reconciles InventoryItem.quantity to match reality
    (writes an ADJUST StockMovement), same as routers/inventory.py's existing
    /adjust endpoint — a count IS an adjustment, just one with a declared
    "expected" value to compare against first.
    """
    __tablename__ = "stock_counts"

    id                 = Column(Integer, primary_key=True, index=True)
    restaurant_id      = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    # RESTRICT (explicit): a physical-count audit record — see migration 028.
    inventory_item_id  = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    # Snapshot of what the system believed at count time — captured explicitly
    # rather than re-derived later, so a later query can't silently change
    # what this count "found" as data continues to move.
    expected_quantity  = Column(Float, nullable=False)
    counted_quantity   = Column(Float, nullable=False)
    counted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    counted_at         = Column(DateTime, default=utcnow)
    notes              = Column(Text, default="")

    restaurant      = relationship("Restaurant")
    inventory_item  = relationship("InventoryItem")
    counted_by      = relationship("User")

    __table_args__ = (
        Index("ix_stock_counts_restaurant_item", "restaurant_id", "inventory_item_id"),
    )


class CashDrawerCount(Base):
    """
    Cash-drawer reconciliation (Sprint 4). Scoped honestly: there's no bank
    feed in this codebase, so a three-way till/M-Pesa/bank reconciliation
    isn't buildable yet. This is the buildable half — a staff member enters
    what they physically counted in the drawer at shift end; expected_amount
    is computed from Order rows (payment_method=CASH, is_paid=True) for the
    same window, same "independent physical check vs system belief" pattern
    as StockCount above. See ai/cash_reconciliation/intelligence.py.
    """
    __tablename__ = "cash_drawer_counts"

    id               = Column(Integer, primary_key=True, index=True)
    restaurant_id    = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    # Optional — a count doesn't require a formal clocked LaborShift to exist
    # (some restaurants reconcile per-till, not per-person). RESTRICT: an
    # audit record must not silently lose its shift reference.
    labor_shift_id   = Column(Integer, ForeignKey("labor_shifts.id", ondelete="RESTRICT"), nullable=True)
    window_start     = Column(DateTime, nullable=False)
    window_end       = Column(DateTime, nullable=False)
    # Snapshot at count time, same reasoning as StockCount.expected_quantity —
    # captured explicitly so a later query can't silently change what this
    # count "found" as more orders land.
    expected_amount_cents = Column(Integer, nullable=False)
    counted_amount_cents  = Column(Integer, nullable=False)
    counted_by_user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    counted_at            = Column(DateTime, default=utcnow)
    notes                 = Column(Text, default="")

    restaurant   = relationship("Restaurant")
    labor_shift  = relationship("LaborShift")
    counted_by   = relationship("User")

    __table_args__ = (
        Index("ix_cash_drawer_counts_restaurant_window", "restaurant_id", "window_start"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 10: AGENT EVALUATION — PREDICTION TRACKING
# ─────────────────────────────────────────────────────────────────────────────

class AgentPrediction(Base):
    """
    Records every agent prediction with its actual outcome.
    Powers: model accuracy tracking, confidence calibration, trust metrics.

    Examples:
      - Revenue forecast: predicted KES 120k, actual KES 117k → 2.5% error
      - Pricing: predicted +15% revenue after surge, actual +11% → recalibrate
      - Slow day alert: predicted slow, actual normal → false positive logged
    """
    __tablename__ = "agent_predictions"

    id                = Column(Integer, primary_key=True, index=True)
    restaurant_id     = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    agent_name        = Column(String, nullable=False)   # "revenue_forecaster", "pricing_intelligence"
    prediction_type   = Column(String, nullable=False)   # "daily_revenue", "price_impact", "demand"
    prediction_date   = Column(Date, nullable=False)     # Date the prediction was FOR (not made)
    made_at           = Column(DateTime, default=utcnow)
    predicted_value   = Column(Float, nullable=False)
    predicted_ci_low  = Column(Float, nullable=True)
    predicted_ci_high = Column(Float, nullable=True)
    actual_value      = Column(Float, nullable=True)     # Filled in after the fact
    error_pct         = Column(Float, nullable=True)     # abs(actual - predicted) / predicted * 100
    within_ci         = Column(Boolean, nullable=True)   # Was actual within confidence interval?
    metadata_json     = Column(Text, default="{}")       # Additional context (JSON string)
    evaluated_at      = Column(DateTime, nullable=True)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_agent_predictions_restaurant_agent", "restaurant_id", "agent_name"),
        Index("ix_agent_predictions_date", "prediction_date"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 12: AGENT EXECUTION OBSERVABILITY
# ─────────────────────────────────────────────────────────────────────────────

class AgentExecution(Base):
    """
    Records every agent execution — success, failure, timing.
    Powers: agent health dashboard, performance monitoring, failure alerting.
    """
    __tablename__ = "agent_executions"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True)
    agent_name    = Column(String, nullable=False)
    function_name = Column(String, nullable=False)
    success       = Column(Boolean, nullable=False)
    execution_ms  = Column(Integer, nullable=True)
    error_message = Column(Text, default="")
    records_processed = Column(Integer, default=0)
    triggered_by  = Column(String, default="scheduler")   # scheduler, api, event, manual
    created_at    = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_agent_executions_name_created", "agent_name", "created_at"),
        Index("ix_agent_executions_success",      "success", "created_at"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 15: AI GOVERNANCE — AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

class AgentAuditLog(Base):
    """
    Immutable audit trail for every AI-driven action that changes data.
    Required for enterprise compliance: what changed, why, who approved.

    action_type examples:
      - price_changed          (from pricing_intelligence approve)
      - whatsapp_sent          (from whatsapp_brain)
      - purchase_recommended   (from supply_chain agent)
      - mpesa_payment_received (from the executive orchestrator)
      - stock_critical_alert   (from the executive orchestrator)
    """
    __tablename__ = "agent_audit_log"

    id             = Column(Integer, primary_key=True, index=True)
    restaurant_id  = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    action_type    = Column(String, nullable=False)
    agent_name     = Column(String, nullable=False)
    entity_type    = Column(String, nullable=True)   # "menu_item", "order", "inventory_item"
    entity_id      = Column(Integer, nullable=True)
    before_state   = Column(Text, default="{}")      # JSON snapshot before action
    after_state    = Column(Text, default="{}")       # JSON snapshot after action
    reasoning      = Column(Text, default="")         # Why the agent made this decision
    data_sources   = Column(Text, default="[]")       # JSON list of data used
    approved_by    = Column(String, default="system") # user email or "auto"
    recommendation_id = Column(Integer, nullable=True)  # Links to PricingRecommendation if applicable
    created_at     = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_audit_log_restaurant_created", "restaurant_id", "created_at"),
        Index("ix_audit_log_action_type",        "action_type"),
    )


class NotificationOutbox(Base):
    """
    Durable record of a FAILED event-bus handler delivery (audit remediation,
    Tier 2 item 5). events/bus.py's emit() previously logged and dropped a
    failed handler call — a WhatsApp/push notification that failed to send was
    gone for good, and emit_async()'s fire-and-forget daemon thread lost
    anything in flight on a process restart. A row here is written only when a
    handler raises (not on every successful delivery, which stays purely
    in-process as before); main.py's scheduler retries pending/failed rows
    every 5 minutes via events.bus.sweep_outbox(), looking the handler back up
    by (event_type, handler_name) from the live subscription registry.

    Handlers are not guaranteed idempotent — a handler that partially acted
    before raising (e.g. sent a message, then failed on a follow-up DB write)
    can double-fire on retry. Documented, accepted tradeoff: at-least-once
    delivery without a full transactional-outbox rewrite of every handler.
    """
    __tablename__ = "notification_outbox"

    id            = Column(Integer, primary_key=True, index=True)
    event_type    = Column(String, nullable=False)
    handler_name  = Column(String, nullable=False)
    payload       = Column(Text, nullable=False)   # JSON
    status        = Column(String, nullable=False, default="pending")  # pending | failed | delivered | dead
    attempts      = Column(Integer, nullable=False, default=1)
    last_error    = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=utcnow)
    last_attempt_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_notification_outbox_status_created", "status", "created_at"),
    )


class CustomerConsent(Base):
    """
    Minimal consent record for customer-facing data collection (public order
    checkout today; any future customer-facing flow — e.g. WhatsApp reservation
    booking — must record consent the same way before processing PII).
    Append-only by convention (never update/delete a row) — matches
    AgentAuditLog's pattern. Deliberately NOT the abandoned restaurant-agent/
    tree's full DPA vault/ZKP/tokenization system — that was unbuilt/
    non-functional theater (directives/012_agentic_roadmap.md); this is the
    real legal minimum: what was agreed to, by whom, when, for what purpose.
    """
    __tablename__ = "customer_consents"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    customer_phone = Column(String, nullable=False)
    purpose       = Column(String, nullable=False)   # e.g. "order_checkout", "reservation_booking"
    consented_at  = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_customer_consents_restaurant_phone", "restaurant_id", "customer_phone"),
    )


class CustomerOptOut(Base):
    """
    Marketing/communications suppression list. A customer who replies STOP (or
    UNSUBSCRIBE/CANCEL/etc.) to a WhatsApp message is recorded here and is never
    messaged again until they opt back in (START/UNSTOP removes the row).

    Deliberately keyed by phone number ALONE, with no restaurant_id: an inbound
    STOP arrives on the shared Twilio number and cannot be reliably attributed to
    one restaurant, and — more importantly — "stop messaging me" is a person's
    choice that should hold across every sender on the platform. This is a
    suppression list, not tenant data, so global scope is the privacy-safe choice.
    Phone is stored NORMALIZED (payments.mpesa_client.normalize_phone) so it
    matches order/reservation phones regardless of input format.
    """
    __tablename__ = "customer_optouts"

    id            = Column(Integer, primary_key=True, index=True)
    customer_phone = Column(String, nullable=False, unique=True, index=True)  # normalized 2547XXXXXXXX
    source        = Column(String, default="whatsapp_stop")  # how the opt-out was captured
    opted_out_at  = Column(DateTime, default=utcnow)


class TokenUsage(Base):
    """
    Per-tenant LLM token metering (Phase 2 orchestrator). Its own table rather
    than sentinel rows in agent_messages — agent_messages is the outbound
    WhatsApp log and the dashboard's 'recent actions' feed, which metering rows
    would pollute. One row per LLM turn.
    """
    __tablename__ = "token_usage"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    llm_model     = Column(String, nullable=True)
    # Version of the narration prompt that produced this turn. Lets AIOps trace a
    # shift in token spend or grounding rate back to a specific prompt change
    # instead of guessing (see ai/reasoning/narrator.py::PROMPT_VERSION).
    prompt_version = Column(String, nullable=True)
    input_tokens  = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at    = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_token_usage_restaurant_created", "restaurant_id", "created_at"),
    )


class CustomerFeedback(Base):
    """
    Lightweight customer rating captured over the messaging channel — a customer
    replies "1".."5" to their receipt. Low scores (<=2) trigger a private owner
    alert for service recovery. Kept intentionally minimal; not a full reviews
    system.
    """
    __tablename__ = "customer_feedback"

    id             = Column(Integer, primary_key=True, index=True)
    restaurant_id  = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    order_id       = Column(Integer, ForeignKey("orders.id"), nullable=True)
    customer_phone = Column(String, default="")
    rating         = Column(Integer, nullable=False)
    comment        = Column(Text, default="")
    created_at     = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_customer_feedback_restaurant_created", "restaurant_id", "created_at"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW ENGINE (Phase 8) — durable, multi-step agentic processes
# ─────────────────────────────────────────────────────────────────────────────

class WorkflowRun(Base):
    """
    One durable run of a workflow template (e.g. a low-stock → reorder → notify
    process). State lives here, in the DB, NOT in memory — so a run survives a
    restart and can pause for hours on a human approval or an external reply.

    status: running | awaiting | completed | failed | cancelled
      - awaiting: paused on a human_approval or wait_external step until resumed.
    """
    __tablename__ = "workflow_runs"

    id            = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    template      = Column(String, nullable=False)
    status        = Column(String, nullable=False, default="running")
    context_json  = Column(Text, default="{}")   # accumulated data passed between steps
    current_step  = Column(Integer, default=0)    # index of the next step to run
    created_at    = Column(DateTime, default=utcnow)
    updated_at    = Column(DateTime, default=utcnow, onupdate=utcnow)

    restaurant = relationship("Restaurant")
    steps      = relationship("WorkflowStep", back_populates="run",
                              order_by="WorkflowStep.seq", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workflow_runs_restaurant_status", "restaurant_id", "status"),
    )


class WorkflowStep(Base):
    """
    One step of a workflow run. step_type drives executor behaviour:
      agent_call     — runs a deterministic handler, then auto-advances.
      human_approval — pauses the run (awaiting) until an owner approves/rejects.
      wait_external  — pauses until an external event resumes it (e.g. supplier reply).
      notify         — sends an owner notification, then auto-advances.

    status: pending | running | done | awaiting | skipped | failed
    """
    __tablename__ = "workflow_steps"

    id           = Column(Integer, primary_key=True, index=True)
    # CASCADE: matches the existing ORM cascade="all, delete-orphan" on
    # WorkflowRun.steps — see migration 028.
    run_id       = Column(Integer, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    seq          = Column(Integer, nullable=False)
    name         = Column(String, nullable=False)
    step_type    = Column(String, nullable=False)
    status       = Column(String, nullable=False, default="pending")
    output_json  = Column(Text, default="{}")
    error        = Column(Text, default="")
    created_at   = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    run = relationship("WorkflowRun", back_populates="steps")

    __table_args__ = (
        Index("ix_workflow_steps_run_seq", "run_id", "seq"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTERPRISE HIERARCHY (Phase 10) — chains / franchises above Restaurant
# ─────────────────────────────────────────────────────────────────────────────

class Organization(Base):
    """
    A chain/franchise grouping several restaurants under one tenant. Optional —
    single-location tenants never create one. Cross-location benchmarking and the
    enterprise audit center scope to an organization.
    """
    __tablename__ = "organizations"

    id         = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name       = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    tenant = relationship("Tenant")


class Region(Base):
    """A geographic/operational grouping of restaurants within an organization
    (e.g. 'Nairobi', 'Coast'), for regional-manager scoping and roll-ups."""
    __tablename__ = "regions"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    name            = Column(String, nullable=False)
    manager_email   = Column(String, default="")
    created_at      = Column(DateTime, default=utcnow)

    organization = relationship("Organization")
