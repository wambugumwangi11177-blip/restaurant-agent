from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime, date, time


class StrictModel(BaseModel):
    """Base for all request/response schemas: rejects unrecognized fields with a
    422 instead of silently dropping them. Closes threat-model risk R6 — a client
    (or attacker) sending an unexpected field no longer has it quietly ignored.
    Output models that read from ORM objects add `from_attributes=True` on top of
    this via their own model_config (extra="forbid" is safe there: attribute-based
    validation only ever reads declared fields)."""
    model_config = ConfigDict(extra="forbid")

# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────
class UserBase(StrictModel):
    email: str

class UserCreate(UserBase):
    password: str
    tenant_name: str

class User(UserBase):
    id: int
    is_active: bool = True
    role: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class Token(StrictModel):
    access_token: str
    token_type: str

class TokenData(StrictModel):
    email: Optional[str] = None

# ──────────────────────────────────────────────
# MENU
# ──────────────────────────────────────────────
class MenuItemBase(StrictModel):
    name: str
    price: int = Field(ge=0)  # In cents
    category: str
    description: str = ""
    is_available: bool = True
    image_url: str = ""
    avg_prep_minutes: float = Field(default=10.0, ge=0)

class MenuItemCreate(MenuItemBase):
    pass

class MenuItemUpdate(StrictModel):
    name: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    category: Optional[str] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None
    image_url: Optional[str] = None
    avg_prep_minutes: Optional[float] = Field(default=None, ge=0)

class MenuItem(MenuItemBase):
    id: int
    restaurant_id: int

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────
class OrderItemCreate(StrictModel):
    menu_item_id: int
    quantity: int = Field(default=1, gt=0)

class OrderCreate(StrictModel):
    items: List[OrderItemCreate]
    order_type: str = "dine_in"          # dine_in, takeout, delivery
    delivery_channel: str = "walk_in"    # walk_in, app, uber_eats, bolt_food, glovo
    payment_method: str = "pending"      # cash, mpesa, card, pending
    customer_name: str = ""
    customer_phone: str = ""
    table_number: Optional[int] = None
    notes: str = ""
    consent: bool = False   # required True on the public (customer-facing) endpoint only

class OrderItemOut(StrictModel):
    id: int
    menu_item_id: int
    quantity: int
    unit_price: int
    item_name: str = ""
    prep_station: str = "main"

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class OrderOut(StrictModel):
    id: int
    status: str
    order_type: str
    delivery_channel: str
    payment_method: str
    is_paid: bool
    customer_name: str
    customer_phone: str
    table_number: Optional[int]
    total: int
    notes: str
    created_at: datetime
    completed_at: Optional[datetime]
    items: List[OrderItemOut] = []

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class OrderStatusUpdate(StrictModel):
    status: str   # pending, prep, ready, served, cancelled

class OrderPaymentUpdate(StrictModel):
    payment_method: str  # cash, mpesa, card
    is_paid: bool = True

class OrderDetailsUpdate(StrictModel):
    """Covers the manual edits that don't change status/payment: correcting
    customer details taken down wrong at order time, and appending staff
    notes (kitchen call-outs, void/cancel reasons) to an existing order."""
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    notes: Optional[str] = None


# ──────────────────────────────────────────────
# KITCHEN INCIDENTS — remakes / quality issues (migration 037)
# ──────────────────────────────────────────────
class KitchenIncidentCreate(StrictModel):
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None
    incident_type: str = Field(pattern="^(remake|quality_issue|other)$")
    reason: str = ""

class KitchenIncidentOut(StrictModel):
    id: int
    restaurant_id: int
    order_id: Optional[int]
    order_item_id: Optional[int]
    incident_type: str
    reason: str
    reported_by_user_id: Optional[int]
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# INVENTORY
# ──────────────────────────────────────────────
class InventoryItemCreate(StrictModel):
    item_name: str
    quantity: float = Field(default=0, ge=0)
    unit: str = "kg"
    cost_per_unit: float = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    expiry_days: int = Field(default=30, ge=0)

class InventoryItemUpdate(StrictModel):
    item_name: Optional[str] = None
    quantity: Optional[float] = Field(default=None, ge=0)
    unit: Optional[str] = None
    cost_per_unit: Optional[float] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
    expiry_days: Optional[int] = Field(default=None, ge=0)

class InventoryItemOut(StrictModel):
    id: int
    item_name: str
    quantity: float
    unit: str
    cost_per_unit: float
    low_stock_threshold: int
    expiry_days: int
    par_level: Optional[float] = None            # directive 018
    default_supplier_id: Optional[int] = None     # directive 018

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class StockReceive(StrictModel):
    quantity: float = Field(gt=0)
    cost_per_unit: Optional[float] = Field(default=None, ge=0)
    supplier: str = ""

class StockAdjust(StrictModel):
    quantity: float     # Positive = add, negative = remove
    reason: str = ""    # waste, breakage, correction

# ──────────────────────────────────────────────
# RESERVATIONS
# ──────────────────────────────────────────────
class ReservationCreate(StrictModel):
    customer_name: str
    customer_phone: str = ""
    customer_email: str = ""
    party_size: int = Field(default=2, gt=0)
    reservation_date: date
    reservation_time: time
    duration_minutes: int = Field(default=90, gt=0)
    table_id: Optional[int] = None
    deposit_paid: bool = False
    notes: str = ""

class ReservationOut(StrictModel):
    id: int
    customer_name: str
    customer_phone: str
    customer_email: str
    party_size: int
    reservation_date: date
    # Optional/nullable so the whole /reservations list doesn't 500 on a single
    # legacy row with a null timestamp — found 2026-07-07: 150 seeded
    # reservations had created_at=None, which failed response validation and
    # took down the entire bookings page. reservation_time guarded too.
    reservation_time: Optional[time] = None
    duration_minutes: int
    status: str
    deposit_paid: bool
    notes: str
    table_id: Optional[int]
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class ReservationStatusUpdate(StrictModel):
    status: str  # confirmed, cancelled, completed, no_show

class AvailableTableOut(StrictModel):
    """Best-fit-first suggestion — same ranking find_available_tables()
    already used server-side for the create-time conflict check, now also
    exposed for a host to browse before booking."""
    table_id: int
    table_number: int
    capacity: int

class ReservationUpdate(StrictModel):
    """General edit — changing details of a booking that's already on the
    books (party size grew, customer called to move the time, assigning/
    moving which table it's seated at). Distinct from
    ReservationStatusUpdate, which only ever changes `status`."""
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    party_size: Optional[int] = Field(default=None, gt=0)
    reservation_date: Optional[date] = None
    reservation_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, gt=0)
    table_id: Optional[int] = None
    deposit_paid: Optional[bool] = None
    notes: Optional[str] = None


# ──────────────────────────────────────────────
# TABLES — floor management (part of the `reservations` domain; directive
# 015 has no separate matrix row for tables, so these reuse reservations'
# RW tuple: Owner, Manager, Supervisor, Waiter).
# ──────────────────────────────────────────────
class TableCreate(StrictModel):
    table_number: int = Field(gt=0)
    capacity: int = Field(default=4, gt=0)

class TableUpdate(StrictModel):
    table_number: Optional[int] = Field(default=None, gt=0)
    capacity: Optional[int] = Field(default=None, gt=0)

class TableStatusUpdate(StrictModel):
    status: str  # available, occupied, reserved, cleaning

class TableOut(StrictModel):
    id: int
    restaurant_id: int
    table_number: int
    capacity: int
    status: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# STAFF ROSTER & ROLES (directive 015)
# ──────────────────────────────────────────────
class StaffMemberCreate(StrictModel):
    name: str
    role_title: str = ""
    hourly_rate: int = Field(default=0, ge=0)
    phone: Optional[str] = None
    # If set, a User account is created and linked. staff_role is required
    # whenever a login is granted — no default that silently grants more
    # access than intended (directive 015).
    create_login: bool = False
    email: Optional[str] = None
    password: Optional[str] = None
    staff_role: Optional[str] = None   # one of StaffRole's values, required if create_login

class StaffMemberUpdate(StrictModel):
    name: Optional[str] = None
    role_title: Optional[str] = None
    hourly_rate: Optional[int] = Field(default=None, ge=0)
    phone: Optional[str] = None
    is_active: Optional[bool] = None

class StaffMemberOut(StrictModel):
    id: int
    restaurant_id: int
    user_id: Optional[int]
    name: str
    role_title: str
    hourly_rate: int
    phone: Optional[str]
    is_active: bool
    staff_role: Optional[str] = None   # from the linked User, if any

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class StaffRoleAssign(StrictModel):
    staff_role: str   # one of StaffRole's values


# ──────────────────────────────────────────────
# ATTENDANCE — clock in/out (+ optional GPS), migration 037
# ──────────────────────────────────────────────
class ClockInBody(StrictModel):
    lat: Optional[float] = None
    lng: Optional[float] = None

class ClockOutBody(StrictModel):
    lat: Optional[float] = None
    lng: Optional[float] = None

class LaborShiftOut(StrictModel):
    id: int
    restaurant_id: int
    staff_member_id: int
    staff_name: Optional[str] = None
    shift_date: date
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    actual_hours: Optional[float] = None
    labor_cost: Optional[int] = None
    clock_in_flagged: bool = False

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class AttendanceStatusOut(StrictModel):
    clocked_in: bool
    shift: Optional[LaborShiftOut] = None


class ImpersonateTarget(StrictModel):
    id: int
    email: str
    staff_role: Optional[str] = None


class ImpersonateResponse(StrictModel):
    access_token: str
    token_type: str = "bearer"
    target: ImpersonateTarget
    expires_in_minutes: int


class ImpersonationLogEntry(StrictModel):
    session_id: int
    impersonator_email: str
    target_email: str
    started_at: datetime
    expires_at: datetime
    ended_at: Optional[datetime] = None
    status: str   # "active" | "expired" | "ended"


# ──────────────────────────────────────────────
# STOCK CUSTODY (directive 016)
# ──────────────────────────────────────────────
class StockTransferCreate(StrictModel):
    inventory_item_id: int
    quantity: float = Field(gt=0)
    unit: str = ""
    from_location: str = "store"
    to_location: str = "kitchen"
    notes: str = ""

class StockTransferConfirm(StrictModel):
    confirmed_quantity: float
    notes: str = ""

class StockTransferOut(StrictModel):
    id: int
    restaurant_id: int
    inventory_item_id: int
    quantity: Optional[float]   # null while status == "requested" (directive 017)
    unit: str
    from_location: str
    to_location: str
    status: str
    requested_by_user_id: Optional[int] = None
    requested_at: Optional[datetime] = None
    initiated_by_user_id: Optional[int]
    initiated_at: Optional[datetime]
    confirmed_by_user_id: Optional[int]
    confirmed_at: Optional[datetime]
    confirmed_quantity: Optional[float]
    notes: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# Kitchen-initiated ("pull") requisition — directive 017. No quantity: the
# kitchen is asking, not declaring; the storekeeper commits a quantity at
# fulfil time via StockTransferFulfill.
class StockTransferRequest(StrictModel):
    inventory_item_id: int
    from_location: str = "store"
    to_location: str = "kitchen"
    notes: str = ""

class StockTransferFulfill(StrictModel):
    quantity: float
    unit: str = ""
    notes: str = ""


# ──────────────────────────────────────────────
# RECIPES (directive 017) — what a menu item's dish is made of
# ──────────────────────────────────────────────
class MenuIngredientCreate(StrictModel):
    inventory_item_id: int
    quantity_per_serving: float = Field(gt=0)
    is_critical: bool = True

class MenuIngredientUpdate(StrictModel):
    quantity_per_serving: Optional[float] = Field(default=None, gt=0)
    is_critical: Optional[bool] = None

class MenuIngredientOut(StrictModel):
    id: int
    menu_item_id: int
    inventory_item_id: int
    quantity_per_serving: float
    is_critical: bool
    # Denormalized for the editor UI so it doesn't need a second round-trip
    # per ingredient just to show a name/unit next to the quantity.
    item_name: Optional[str] = None
    unit: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ──────────────────────────────────────────────
# PHYSICAL STOCK COUNTS (directive 017)
# ──────────────────────────────────────────────
class StockCountCreate(StrictModel):
    inventory_item_id: int
    counted_quantity: float
    notes: str = ""

class StockCountOut(StrictModel):
    id: int
    restaurant_id: int
    inventory_item_id: int
    expected_quantity: float
    counted_quantity: float
    counted_by_user_id: int
    counted_at: Optional[datetime]
    notes: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ──────────────────────────────────────────────
# SUPPLIERS & PURCHASE ORDERS (directive 018) — par-level reordering
# ──────────────────────────────────────────────
class SupplierCreate(StrictModel):
    name: str
    contact_phone: str = ""
    contact_email: str = ""
    avg_lead_days: float = Field(default=1.0, ge=0)
    notes: str = ""

class SupplierUpdate(StrictModel):
    name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    avg_lead_days: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    notes: Optional[str] = None

class SupplierOut(StrictModel):
    id: int
    restaurant_id: int
    name: str
    contact_phone: str
    contact_email: str
    avg_lead_days: float
    reliability_score: float
    is_active: bool
    notes: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class InventoryReorderSettingsUpdate(StrictModel):
    par_level: Optional[float] = None
    default_supplier_id: Optional[int] = None

class PurchaseOrderOut(StrictModel):
    id: int
    restaurant_id: int
    supplier_id: int
    inventory_item_id: Optional[int]
    quantity_ordered: float
    quantity_received: Optional[float]
    unit: str
    cost_per_unit: int
    total_cost: int
    status: str
    ordered_at: Optional[datetime]
    expected_at: Optional[datetime]
    delivered_at: Optional[datetime]
    notes: str
    # Denormalized for the approve/receive UI so it doesn't need a second
    # round-trip just to show names next to ids.
    supplier_name: Optional[str] = None
    item_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class PurchaseOrderReceive(StrictModel):
    quantity_received: float
    notes: str = ""


# ──────────────────────────────────────────────
# BILLING (Phase 10)
# ──────────────────────────────────────────────
class PlanUpdate(StrictModel):
    plan: str


# ──────────────────────────────────────────────
# PRODUCT ANALYTICS (Phase 8)
# ──────────────────────────────────────────────
class ProductEventTrack(StrictModel):
    event_name: str = ""
    properties: dict = {}


# ──────────────────────────────────────────────
# AI ROUTER — bodies for routers/ai.py
# ──────────────────────────────────────────────
class PricingRejectBody(StrictModel):
    reason: str = ""

class StrategyGoalBody(StrictModel):
    goal: str = ""
    timeframe: str = ""

class StrategyPlanBody(StrictModel):
    goal: str = ""
    horizon_weeks: int = Field(default=4, gt=0)

class PluginInvokeBody(StrictModel):
    payload: dict = {}
    approved: bool = False

class WorkflowResumeBody(StrictModel):
    decision: str = "approve"
    payload: Optional[dict] = None

class SimulateBody(StrictModel):
    change: dict = {}

class MarketingPromoBody(StrictModel):
    offer_text: str = ""

class ExplainBody(StrictModel):
    item: Optional[dict] = None
    label: str = ""

# ──────────────────────────────────────────────
# NOTIFICATIONS (in-app feed + Web Push)
# ──────────────────────────────────────────────
class PushSubscriptionCreate(StrictModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None

class PushSubscriptionOut(StrictModel):
    id: int
    endpoint: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class PushUnsubscribeBody(StrictModel):
    endpoint: str

class NotificationOut(StrictModel):
    id: int
    title: str
    body: str
    event_type: str
    url: Optional[str] = None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class NotificationListOut(StrictModel):
    items: List[NotificationOut]
    unread_count: int

# ──────────────────────────────────────────────
# SUPPORT TICKETS
# ──────────────────────────────────────────────
class SupportTicketCreate(StrictModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)

class SupportTicketMessageCreate(StrictModel):
    body: str = Field(min_length=1, max_length=4000)

class SupportTicketMessageOut(StrictModel):
    id: int
    sender_id: int
    sender_email: str
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class SupportTicketOut(StrictModel):
    id: int
    subject: str
    status: str
    created_by_id: int
    created_by_email: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class SupportTicketDetailOut(StrictModel):
    id: int
    subject: str
    status: str
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    messages: List[SupportTicketMessageOut]

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class SupportTicketStatusUpdate(StrictModel):
    status: str
