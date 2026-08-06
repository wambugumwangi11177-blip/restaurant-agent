from pydantic import BaseModel, ConfigDict
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
    price: int  # In cents
    category: str
    description: str = ""
    is_available: bool = True

class MenuItemCreate(MenuItemBase):
    pass

class MenuItemUpdate(StrictModel):
    name: Optional[str] = None
    price: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None

class MenuItem(MenuItemBase):
    id: int
    restaurant_id: int

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────
class OrderItemCreate(StrictModel):
    menu_item_id: int
    quantity: int = 1

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

# ──────────────────────────────────────────────
# INVENTORY
# ──────────────────────────────────────────────
class InventoryItemCreate(StrictModel):
    item_name: str
    quantity: float = 0
    unit: str = "kg"
    cost_per_unit: float = 0
    low_stock_threshold: int = 10
    expiry_days: int = 30

class InventoryItemUpdate(StrictModel):
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    cost_per_unit: Optional[float] = None
    low_stock_threshold: Optional[int] = None
    expiry_days: Optional[int] = None

class InventoryItemOut(StrictModel):
    id: int
    item_name: str
    quantity: float
    unit: str
    cost_per_unit: float
    low_stock_threshold: int
    expiry_days: int

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class StockReceive(StrictModel):
    quantity: float
    cost_per_unit: Optional[float] = None
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
    party_size: int = 2
    reservation_date: date
    reservation_time: time
    duration_minutes: int = 90
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

# ──────────────────────────────────────────────
# RECIPES (MenuItem → InventoryItem links)
# ──────────────────────────────────────────────
# The write path for MenuIngredient, which had no API at all until 2026-08-06:
# the table was in the schema and read by the knowledge graph, but nothing could
# create a row, so no restaurant could ever describe what a dish is made of.

class RecipeLineIn(StrictModel):
    inventory_item_id: int
    quantity_per_serving: float
    # False marks a garnish — present in the recipe and costed, but its absence
    # doesn't stop the dish being made. The orchestrator's cascade analysis
    # already relies on this distinction.
    is_critical: bool = True


class RecipeReplace(StrictModel):
    """
    Whole-recipe replace rather than per-line CRUD. A recipe is edited as one
    thing ("here is what goes into this dish"), and replace-in-full removes the
    partial-update states — a half-saved recipe would silently under-deduct
    stock on every subsequent sale.
    """
    ingredients: List[RecipeLineIn]
    # Recompute MenuItem.cost_price from the recipe on save. On by default: the
    # entire point of recipes is that cost stops being a number someone typed
    # once and drifted from reality.
    sync_cost_price: bool = True


class RecipeLineOut(StrictModel):
    id: int
    inventory_item_id: int
    item_name: str
    unit: str
    quantity_per_serving: float
    is_critical: bool
    cost_per_unit: float      # whole KES — InventoryItem's native unit
    line_cost_cents: int      # quantity × cost_per_unit, converted to cents


class RecipeOut(StrictModel):
    menu_item_id: int
    menu_item_name: str
    ingredients: List[RecipeLineOut]
    # None when the dish has no recipe — meaning "unknown", not "free".
    derived_cost_price: Optional[int] = None   # cents
    stored_cost_price: int                     # cents, what pricing/profit read
    cost_price_synced: bool                    # do the two agree?

# ──────────────────────────────────────────────
# STAFF & SHIFTS
# ──────────────────────────────────────────────
# The write path for StaffMember / LaborShift. Both tables shipped with the
# labor-intelligence work and had NO writer anywhere in the codebase — not even
# the demo seeder — so ai/labor/intelligence.py returned _empty_response() for
# every restaurant, and ai/roi/savings.py always fell back to its
# DEFAULT_HOURLY_RATE_CENTS constant instead of using real wages.

class StaffMemberCreate(StrictModel):
    name: str
    role_title: str = ""
    hourly_rate: int = 0          # cents — matches StaffMember.hourly_rate
    user_id: Optional[int] = None  # link to a login, for staff who have one


class StaffMemberUpdate(StrictModel):
    name: Optional[str] = None
    role_title: Optional[str] = None
    hourly_rate: Optional[int] = None
    is_active: Optional[bool] = None


class StaffMemberOut(StrictModel):
    id: int
    name: str
    role_title: str
    hourly_rate: int
    is_active: bool
    user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ShiftCreate(StrictModel):
    staff_member_id: int
    shift_date: date
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    notes: str = ""


class ShiftOut(StrictModel):
    id: int
    staff_member_id: int
    staff_name: str
    shift_date: date
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    scheduled_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    labor_cost: Optional[int] = None    # cents — hours × the staff hourly_rate
    notes: str = ""
