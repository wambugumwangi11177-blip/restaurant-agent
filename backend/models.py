from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SqEnum, DateTime, Float, Text, Date, Time
from sqlalchemy.orm import relationship, declarative_base
import datetime
import enum

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

# ──────────────────────────────────────────────
# TENANT & USER
# ──────────────────────────────────────────────
class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    plan = Column(String, default="free")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    users = relationship("User", back_populates="tenant")
    restaurants = relationship("Restaurant", back_populates="tenant")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(SqEnum(Role), default=Role.STAFF)
    
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
    table_number = Column(Integer, nullable=True)
    customer_name = Column(String, default="")
    total = Column(Integer)  # In cents
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    restaurant = relationship("Restaurant", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="reservations")
    table = relationship("Table", back_populates="reservations")
