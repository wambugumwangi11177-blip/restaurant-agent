from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, time

# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str
    tenant_name: str

class User(UserBase):
    id: int
    is_active: bool = True
    role: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# ──────────────────────────────────────────────
# MENU
# ──────────────────────────────────────────────
class MenuItemBase(BaseModel):
    name: str
    price: int  # In cents
    category: str
    description: str = ""
    is_available: bool = True

class MenuItemCreate(MenuItemBase):
    pass

class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None

class MenuItem(MenuItemBase):
    id: int
    restaurant_id: int

    class Config:
        from_attributes = True

# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────
class OrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = 1

class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    order_type: str = "dine_in"          # dine_in, takeout, delivery
    delivery_channel: str = "walk_in"    # walk_in, app, uber_eats, bolt_food, glovo
    payment_method: str = "pending"      # cash, mpesa, card, pending
    customer_name: str = ""
    customer_phone: str = ""
    table_number: Optional[int] = None
    notes: str = ""

class OrderItemOut(BaseModel):
    id: int
    menu_item_id: int
    quantity: int
    unit_price: int
    item_name: str = ""

    class Config:
        from_attributes = True

class OrderOut(BaseModel):
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

    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: str   # pending, prep, ready, served, cancelled

class OrderPaymentUpdate(BaseModel):
    payment_method: str  # cash, mpesa, card
    is_paid: bool = True

# ──────────────────────────────────────────────
# INVENTORY
# ──────────────────────────────────────────────
class InventoryItemCreate(BaseModel):
    item_name: str
    quantity: float = 0
    unit: str = "kg"
    cost_per_unit: float = 0
    low_stock_threshold: int = 10
    expiry_days: int = 30

class InventoryItemUpdate(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    cost_per_unit: Optional[float] = None
    low_stock_threshold: Optional[int] = None
    expiry_days: Optional[int] = None

class InventoryItemOut(BaseModel):
    id: int
    item_name: str
    quantity: float
    unit: str
    cost_per_unit: float
    low_stock_threshold: int
    expiry_days: int

    class Config:
        from_attributes = True

class StockReceive(BaseModel):
    quantity: float
    cost_per_unit: Optional[float] = None
    supplier: str = ""

class StockAdjust(BaseModel):
    quantity: float     # Positive = add, negative = remove
    reason: str = ""    # waste, breakage, correction

# ──────────────────────────────────────────────
# RESERVATIONS
# ──────────────────────────────────────────────
class ReservationCreate(BaseModel):
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

class ReservationOut(BaseModel):
    id: int
    customer_name: str
    customer_phone: str
    customer_email: str
    party_size: int
    reservation_date: date
    reservation_time: time
    duration_minutes: int
    status: str
    deposit_paid: bool
    notes: str
    table_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class ReservationStatusUpdate(BaseModel):
    status: str  # confirmed, cancelled, completed, no_show
