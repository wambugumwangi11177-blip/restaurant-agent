"""
Test suite for tenant isolation across various endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import Base, get_db
import models

# Test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_isolation.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def create_user_and_login(email, password, tenant_name):
    """Helper to create user and get auth token."""
    # Register
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "tenant_name": tenant_name
        }
    )
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    return response.json()["access_token"]

def test_tenant_isolation_inventory():
    """Test that users can only modify inventory items from their own restaurant."""
    # Create two users
    token1 = create_user_and_login("user1@example.com", "password123", "Restaurant One")
    token2 = create_user_and_login("user2@example.com", "password456", "Restaurant Two")

    # User1 creates inventory item
    response = client.post(
        "/inventory/",
        json={
            "item_name": "Tomatoes",
            "quantity": 10.0,
            "unit": "kg",
            "cost_per_unit": 2.5,
            "low_stock_threshold": 5,
            "expiry_days": 7
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    item_id = response.json()["id"]

    # User2 tries to access user1's inventory item (should fail)
    response = client.get(
        f"/inventory/{item_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    # Should return 404 because item doesn't exist in user2's restaurant context
    # Or could be 403 if ownership check is done before lookup
    assert response.status_code in [403, 404]

    # User1 can access their own item
    response = client.get(
        f"/inventory/{item_id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    assert response.json()["item_name"] == "Tomatoes"

def test_tenant_isolation_menu():
    """Test that users can only modify menu items from their own restaurant."""
    # Create two users
    token1 = create_user_and_login("user1@example.com", "password123", "Restaurant One")
    token2 = create_user_and_login("user2@example.com", "password456", "Restaurant Two")

    # User1 creates menu item
    response = client.post(
        "/menu/",
        json={
            "name": "Caesar Salad",
            "price": 1200,  # $12.00 in cents
            "category": "Salad",
            "description": "Fresh romaine with caesar dressing",
            "is_available": True
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    item_id = response.json()["id"]

    # User2 tries to access user1's menu item (should fail)
    response = client.get(
        f"/menu/{item_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert response.status_code in [403, 404]

    # User1 can access their own item
    response = client.get(
        f"/menu/{item_id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Caesar Salad"

def test_tenant_isolation_orders():
    """Test that users can only see orders from their own restaurant."""
    # Create two users
    token1 = create_user_and_login("user1@example.com", "password123", "Restaurant One")
    token2 = create_user_and_login("user2@example.com", "password456", "Restaurant Two")

    # User1 creates an order (need menu item first)
    menu_response = client.post(
        "/menu/",
        json={
            "name": "Burger",
            "price": 1500,  # $15.00 in cents
            "category": "Main",
            "description": "Beef burger with fries",
            "is_available": True
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    menu_item_id = menu_response.json()["id"]

    # User1 creates order
    order_response = client.post(
        "/orders/",
        json={
            "items": [{"menu_item_id": menu_item_id, "quantity": 2}],
            "order_type": "dine_in",
            "delivery_channel": "walk_in",
            "payment_method": "cash",
            "customer_name": "John Doe",
            "customer_phone": "1234567890"
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert order_response.status_code == 200
    order_id = order_response.json()["id"]

    # User2 tries to access user1's order (should fail or return empty)
    response = client.get(
        f"/orders/{order_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    # Should return 404 since order doesn't exist in user2's context
    assert response.status_code == 404

    # User1 can access their own order
    response = client.get(
        f"/orders/{order_id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == order_id

def test_tenant_isolation_reservations():
    """Test that users can only manage reservations from their own restaurant."""
    # Create two users
    token1 = create_user_and_login("user1@example.com", "password123", "Restaurant One")
    token2 = create_user_and_login("user2@example.com", "password456", "Restaurant Two")

    # User1 creates reservation
    response = client.post(
        "/reservations/",
        json={
            "customer_name": "Jane Smith",
            "customer_phone": "0987654321",
            "customer_email": "jane@example.com",
            "party_size": 4,
            "reservation_date": "2026-06-15",
            "reservation_time": "19:00:00",
            "duration_minutes": 120,
            "table_id": 1,
            "deposit_paid": False,
            "notes": "Window seat preferred"
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    reservation_id = response.json()["id"]

    # User2 tries to access user1's reservation (should fail)
    response = client.get(
        f"/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert response.status_code == 404

    # User1 can access their own reservation
    response = client.get(
        f"/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    assert response.json()["customer_name"] == "Jane Smith"

def test_cross_tenant_modification_blocked():
    """Test that users cannot modify resources belonging to other tenants."""
    # Setup: Create two users and have user1 create resources
    token1 = create_user_and_login("owner1@example.com", "password123", "Restaurant One")
    token2 = create_user_and_login("owner2@example.com", "password456", "Restaurant Two")

    # User1 creates inventory item
    inv_response = client.post(
        "/inventory/",
        json={
            "item_name": "Onions",
            "quantity": 5.0,
            "unit": "kg",
            "cost_per_unit": 1.5,
            "low_stock_threshold": 2,
            "expiry_days": 14
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert inv_response.status_code == 200
    item_id = inv_response.json()["id"]

    # User2 tries to UPDATE user1's inventory item (should be blocked)
    response = client.put(
        f"/inventory/{item_id}",
        json={
            "item_name": "Onions",
            "quantity": 8.0,
            "unit": "kg",
            "cost_per_unit": 1.5,
            "low_stock_threshold": 2,
            "expiry_days": 14
        },
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert response.status_code in [403, 404]

    # User1 can UPDATE their own item
    response = client.put(
        f"/inventory/{item_id}",
        json={
            "item_name": "Onions",
            "quantity": 8.0,
            "unit": "kg",
            "cost_per_unit": 1.5,
            "low_stock_threshold": 2,
            "expiry_days": 14
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 8.0

    # User2 tries to DELETE user1's inventory item (should be blocked)
    response = client.delete(
        f"/inventory/{item_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert response.status_code in [403, 404]

    # Item should still exist for user1
    response = client.get(
        f"/inventory/{item_id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 200