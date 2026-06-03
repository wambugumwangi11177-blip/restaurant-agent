import os
import subprocess
import sys

def run_command(command, cwd=None):
    print(f"Running: {command}")
    try:
        subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            check=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        sys.exit(1)

def setup_db():
    backend_dir = "backend"
    if not os.path.exists(backend_dir):
        print("Backend directory not found. Please run setup.py first.")
        return

    # Install dependencies
    print("Installing DB dependencies...")
    venv_path = os.path.join(backend_dir, "venv")
    if os.name == 'nt':
        pip_cmd = os.path.join(venv_path, "Scripts", "pip")
        alembic_cmd = os.path.join(venv_path, "Scripts", "alembic")
    else:
        pip_cmd = os.path.join(venv_path, "bin", "pip")
        alembic_cmd = os.path.join(venv_path, "bin", "alembic")

    run_command(f"\"{pip_cmd}\" install sqlalchemy alembic psycopg2-binary")

    # Create models.py
    models_path = os.path.join(backend_dir, "models.py")
    if not os.path.exists(models_path):
        print("Creating backend/models.py...")
        with open(models_path, "w") as f:
            f.write("""from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SqEnum, DateTime
from sqlalchemy.orm import relationship, declarative_base
import datetime
import enum

Base = declarative_base()

class Role(enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    STAFF = "staff"

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

class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    name = Column(String)
    price = Column(Integer) # In cents
    category = Column(String)
    
    restaurant = relationship("Restaurant", back_populates="menu_items")

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PREP = "prep"
    READY = "ready"
    SERVED = "served"

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    status = Column(SqEnum(OrderStatus), default=OrderStatus.PENDING)
    total = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="orders")

class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    item_name = Column(String)
    quantity = Column(Integer)
    unit = Column(String)
    low_stock_threshold = Column(Integer)
    
    restaurant = relationship("Restaurant", back_populates="inventory_items")
""")
        print("Created models.py")

    # Initialize Alembic
    if not os.path.exists(os.path.join(backend_dir, "alembic")):
        print("Initializing Alembic...")
        if os.name == 'nt':
             venv_python = os.path.abspath(os.path.join(venv_path, "Scripts", "python.exe"))
        else:
             venv_python = os.path.abspath(os.path.join(venv_path, "bin", "python"))

        run_command(f"\"{venv_python}\" -m alembic init alembic", cwd=backend_dir)
        print("Alembic initialized.")
        print("NOTE: You must manually configure alembic.ini and env.py to use DATABASE_URL and import models.")

if __name__ == "__main__":
    setup_db()
