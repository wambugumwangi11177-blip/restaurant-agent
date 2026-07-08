from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SqEnum, DateTime, Float, Text, Date, Time, Index, UniqueConstraint
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
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(SqEnum(Role), default=Role.STAFF)
    failed_login_attempts = Column(Integer, default=0)   # brute-force lockout (2026-07-07 security pass)
    locked_until = Column(DateTime, nullable=True)         # None = not locked
    last_login_at = Column(DateTime, nullable=True)        # set on successful login (staff-activity record)

    tenant = relationship("Tenant", back_populates="users")

# ──────────────────────────────────────────────
# RESTAURANT & TABLES
# ──────────────────────────────────────────────
class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    name = Column(String)
    address = Column(String)
    owner_phone = Column(String, nullable=True)   # WhatsApp owner routing (was OWNER_PHONE_{id} env var)

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
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    table_number = Column(Integer)
    capacity = Column(Integer, default=4)
    status = Column(SqEnum(TableStatus), default=TableStatus.AVAILABLE)
    
    restaurant = relationship("Restaurant", back_populates="tables")
    reservations = relationship("Reservation", back_populates="table")

# ──────────────────────────────────────────────
# MENU ITEMS (Enhanced for AI)
# ──────────────────────────────────────────────
class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
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
    order_items = relationship("OrderItem", back_populates="menu_item")

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

class OrderItem(Base):
    """Links orders to menu items — critical for menu performance analysis."""
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Integer)  # Snapshot of price at time of order
    
    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")
    prep_time = relationship("PrepTime", back_populates="order_item", uselist=False)

# ──────────────────────────────────────────────
# KDS: PREP TIME TRACKING
# ──────────────────────────────────────────────
class PrepTime(Base):
    """Tracks actual kitchen prep time per order item — powers KDS intelligence."""
    __tablename__ = "prep_times"
    id = Column(Integer, primary_key=True, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id"))
    station = Column(String, default="main")  # grill, fryer, salad, drinks, main
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    actual_minutes = Column(Float, nullable=True)
    
    order_item = relationship("OrderItem", back_populates="prep_time")

# ──────────────────────────────────────────────
# INVENTORY (Enhanced for AI)
# ──────────────────────────────────────────────
class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    item_name = Column(String)
    quantity = Column(Float, default=0)
    unit = Column(String)
    cost_per_unit = Column(Float, default=0)  # For procurement cost tracking
    low_stock_threshold = Column(Integer)
    expiry_days = Column(Integer, default=30)  # Avg shelf life — for spoilage prediction
    # When the owner was last WhatsApped that this item is low/out. The stock
    # check runs every 2h; without this a persistently low item re-alerts every
    # cycle (7 messages/day, per item) until someone restocks. See
    # ai/whatsapp/brain.STOCK_ALERT_COOLDOWN_HOURS. Added by migration 010.
    last_alerted_at = Column(DateTime, nullable=True)

    restaurant = relationship("Restaurant", back_populates="inventory_items")
    movements = relationship("StockMovement", back_populates="inventory_item")

class StockMovement(Base):
    """Tracks inventory in/out — powers depletion prediction and reorder intelligence."""
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"))
    movement_type = Column(SqEnum(StockMovementType))
    quantity = Column(Float)
    reason = Column(String, default="")  # "sale", "waste", "purchase", "adjustment"
    created_at = Column(DateTime, default=utcnow)
    
    inventory_item = relationship("InventoryItem", back_populates="movements")

# ──────────────────────────────────────────────
# RESERVATIONS (New for AI)
# ──────────────────────────────────────────────
class Reservation(Base):
    """Reservation system — powers no-show prediction and revenue-per-seat optimization."""
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=True)
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
    
    restaurant = relationship("Restaurant", back_populates="reservations")
    table = relationship("Table", back_populates="reservations")

# ─────────────────────────────────────────────────────────────────────────────
# EXISTING (from previous release) — keep as-is
# ─────────────────────────────────────────────────────────────────────────────

class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"
    id                      = Column(Integer, primary_key=True, index=True)
    restaurant_id           = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    menu_item_id            = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
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
    menu_item_id        = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    inventory_item_id   = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
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
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True)   # Optional
    name          = Column(String, nullable=False)
    role_title    = Column(String, default="")   # "Head Chef", "Waiter", "Cashier"
    hourly_rate   = Column(Integer, default=0)   # In cents
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")
    shifts     = relationship("LaborShift", back_populates="staff_member")

    __table_args__ = (
        Index("ix_staff_members_restaurant", "restaurant_id"),
    )


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

    staff_member = relationship("StaffMember", back_populates="shifts")
    restaurant   = relationship("Restaurant")

    __table_args__ = (
        Index("ix_labor_shifts_restaurant_date", "restaurant_id", "shift_date"),
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
    is_active         = Column(Boolean, default=True)
    notes             = Column(Text, default="")
    created_at        = Column(DateTime, default=utcnow)

    restaurant     = relationship("Restaurant")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

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
    supplier_id       = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=True)
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
      - price_changed        (from pricing_intelligence approve)
      - whatsapp_sent        (from whatsapp_brain)
      - purchase_recommended (from supply_chain agent)
      - campaign_launched    (from marketing agent)
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
    input_tokens  = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at    = Column(DateTime, default=utcnow)

    restaurant = relationship("Restaurant")

    __table_args__ = (
        Index("ix_token_usage_restaurant_created", "restaurant_id", "created_at"),
    )
