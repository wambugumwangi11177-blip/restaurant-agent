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
