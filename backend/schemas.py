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
# MODIFIERS
# ──────────────────────────────────────────────
class ModifierOptionBase(StrictModel):
    name: str
    price_delta_cents: int = 0
    is_available: bool = True

class ModifierOptionCreate(ModifierOptionBase):
    pass

class ModifierOptionOut(ModifierOptionBase):
    id: int
    group_id: int

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class ModifierGroupBase(StrictModel):
    name: str
    min_selection: int = 0
    max_selection: int = 1
    is_required: bool = False

class ModifierGroupCreate(ModifierGroupBase):
    options: List[ModifierOptionCreate] = []

class ModifierGroupOut(ModifierGroupBase):
    id: int
    options: List[ModifierOptionOut] = []

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────
class OrderItemModifierCreate(StrictModel):
    modifier_option_id: Optional[int] = None
    name: str
    price_delta_cents: int = 0

class OrderItemModifierOut(StrictModel):
    id: int
    name: str
    price_delta_cents: int = 0

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class OrderItemCreate(StrictModel):
    menu_item_id: int
    quantity: int = 1
    notes: str = ""
    modifiers: List[OrderItemModifierCreate] = []

class OrderPaymentCreate(StrictModel):
    payment_method: str  # cash, mpesa, card
    amount_cents: int
    reference: str = ""

class OrderPaymentOut(StrictModel):
    id: int
    payment_method: str
    amount_cents: int
    reference: str = ""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class OrderCreate(StrictModel):
    items: List[OrderItemCreate]
    order_type: str = "dine_in"          # dine_in, takeout, delivery
    delivery_channel: str = "walk_in"    # walk_in, app, uber_eats, bolt_food, glovo
    payment_method: str = "pending"      # cash, mpesa, card, pending
    customer_name: str = ""
    customer_phone: str = ""
    table_number: Optional[int] = None
    notes: str = ""
    consent: bool = False
    discount_cents: int = 0
    discount_reason: str = ""
    tax_cents: int = 0
    service_charge_cents: int = 0
    payments: List[OrderPaymentCreate] = []
    idempotency_key: Optional[str] = None
    attributed_user_id: Optional[int] = None

class OrderItemOut(StrictModel):
    id: int
    menu_item_id: int
    quantity: int
    unit_price: int
    item_name: str = ""
    is_voided: bool = False
    void_reason: str = ""
    notes: str = ""
    modifiers: List[OrderItemModifierOut] = []

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
    discount_cents: int = 0
    discount_reason: str = ""
    void_reason: str = ""
    refund_cents: int = 0
    refund_reason: str = ""
    tax_cents: int = 0
    service_charge_cents: int = 0
    created_at: datetime
    completed_at: Optional[datetime]
    items: List[OrderItemOut] = []
    payments: List[OrderPaymentOut] = []
    attributed_user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class OrderStatusUpdate(StrictModel):
    status: str   # pending, prep, ready, served, cancelled

class OrderPaymentUpdate(StrictModel):
    payment_method: str  # cash, mpesa, card
    is_paid: bool = True
    amount_cents: Optional[int] = None
    reference: str = ""

class OrderVoidRequest(StrictModel):
    void_reason: str

class OrderRefundRequest(StrictModel):
    refund_cents: int
    refund_reason: str


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
    # Human-readable reminder state computed in _res_to_dict (routers/reservations.py):
    # "Not required" | "Deposit paid (KES 1,000)" | "Reminder sent" | "Pending reminder".
    # Found 2026-09-08: the serializer emitted this field but the schema didn't declare
    # it, and with extra="forbid" FastAPI rejected its own response on every
    # reservation endpoint (ResponseValidationError) — 8 test failures.
    reminder_status: str = "Not required"
    notes: str
    table_id: Optional[int]
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class ReservationStatusUpdate(StrictModel):
    status: str  # confirmed, cancelled, completed, no_show

# ──────────────────────────────────────────────
# RECIPE / BOM
# ──────────────────────────────────────────────
class RecipeIngredientCreate(StrictModel):
    inventory_item_id: int
    quantity_per_serving: float = 1.0
    is_critical: bool = True

class RecipeIngredientOut(StrictModel):
    id: int
    menu_item_id: int
    inventory_item_id: int
    item_name: str = ""
    unit: str = ""
    cost_per_unit: float = 0.0
    quantity_per_serving: float
    is_critical: bool

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# TILL SESSIONS
# ──────────────────────────────────────────────
class TillSessionOpen(StrictModel):
    opening_float_cents: int = 0
    notes: str = ""

class TillSessionClose(StrictModel):
    closing_counted_cents: int
    variance_reason: str = ""
    notes: str = ""

class TillSessionOut(StrictModel):
    id: int
    user_id: int
    user_name: str = ""
    opening_float_cents: int
    closing_counted_cents: Optional[int] = None
    expected_cash_cents: Optional[int] = None
    variance_cents: Optional[int] = None
    variance_reason: str = ""
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    notes: str = ""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# INVENTORY COUNT SHEETS & WASTE
# ──────────────────────────────────────────────
class InventoryCountLineCreate(StrictModel):
    inventory_item_id: int
    counted_qty: float

class InventoryCountLineOut(StrictModel):
    id: int
    inventory_item_id: int
    item_name: str = ""
    unit: str = ""
    theoretical_qty: float
    counted_qty: float
    variance_qty: float

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class InventoryCountCreate(StrictModel):
    notes: str = ""
    lines: List[InventoryCountLineCreate] = []

class InventoryCountOut(StrictModel):
    id: int
    user_id: int
    count_date: date
    status: str
    notes: str
    created_at: datetime
    posted_at: Optional[datetime] = None
    lines: List[InventoryCountLineOut] = []

    model_config = ConfigDict(from_attributes=True, extra="forbid")

class WasteLogCreate(StrictModel):
    inventory_item_id: int
    quantity: float
    reason: str  # spoil, trim, staff_meal, error, theft
    notes: str = ""

class WasteLogOut(StrictModel):
    id: int
    inventory_item_id: int
    item_name: str = ""
    user_id: int
    quantity: float
    unit: str
    reason: str
    cost_cents: int
    notes: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ──────────────────────────────────────────────
# RESTAURANT SETTINGS
# ──────────────────────────────────────────────
class RestaurantSettingUpdate(StrictModel):
    tax_rate_percent: Optional[float] = None
    service_charge_percent: Optional[float] = None
    receipt_header: Optional[str] = None
    receipt_footer: Optional[str] = None
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None
    lunch_start: Optional[str] = None
    lunch_end: Optional[str] = None
    dinner_start: Optional[str] = None
    dinner_end: Optional[str] = None
    stations_json: Optional[str] = None
    tenders_json: Optional[str] = None
    kitchen_printer_url: Optional[str] = None
    receipt_printer_url: Optional[str] = None

class RestaurantSettingOut(StrictModel):
    tax_rate_percent: float
    service_charge_percent: float
    receipt_header: str
    receipt_footer: str
    currency: str
    timezone: str
    opening_time: str
    closing_time: str
    lunch_start: str
    lunch_end: str
    dinner_start: str
    dinner_end: str
    stations_json: str
    tenders_json: str
    kitchen_printer_url: str
    receipt_printer_url: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")

