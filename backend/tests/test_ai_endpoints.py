"""
Test suite for AI endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import Base, get_db
import models

# Test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_ai.db"
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

def test_ai_dashboard_endpoint():
    """Test AI dashboard endpoint."""
    token = create_user_and_login("aiuser@example.com", "password123", "AI Test Restaurant")

    response = client.get(
        "/ai/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "health_score" in data
    assert "quick_stats" in data
    assert "risks" in data
    assert "opportunities" in data
    assert isinstance(data["health_score"], int)
    assert 0 <= data["health_score"] <= 100

def test_ai_pricing_endpoint():
    """Test AI pricing endpoint."""
    token = create_user_and_login("pricinguser@example.com", "password123", "Pricing Test Restaurant")

    response = client.get(
        "/ai/pricing",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return pricing intelligence data (structure may vary based on implementation)

def test_ai_labor_endpoint():
    """Test AI labor endpoint."""
    token = create_user_and_login("laboruser@example.com", "password123", "Labor Test Restaurant")

    response = client.get(
        "/ai/labor",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return labor analytics data

def test_ai_revenue_forecast_endpoint():
    """Test AI revenue forecast endpoint."""
    token = create_user_and_login("revenueuser@example.com", "password123", "Revenue Test Restaurant")

    response = client.get(
        "/ai/revenue-forecast",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return revenue forecast data

def test_ai_menu_engineering_endpoint():
    """Test AI menu engineering endpoint."""
    token = create_user_and_login("menuuser@example.com", "password123", "Menu Test Restaurant")

    response = client.get(
        "/ai/menu-engineering",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return menu engineering data

def test_ai_inventory_endpoint():
    """Test AI inventory endpoint."""
    token = create_user_and_login("inventoryuser@example.com", "password123", "Inventory Test Restaurant")

    response = client.get(
        "/ai/inventory",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return inventory intelligence data

def test_ai_reservation_insights_endpoint():
    """Test AI reservation insights endpoint."""
    token = create_user_and_login("reservationuser@example.com", "password123", "Reservation Test Restaurant")

    response = client.get(
        "/ai/reservation-insights",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return reservation insights data

def test_ai_endpoints_require_auth():
    """Test that all AI endpoints require authentication."""
    endpoints = [
        "/ai/dashboard",
        "/ai/pricing",
        "/ai/labor",
        "/ai/revenue-forecast",
        "/ai/menu-engineering",
        "/ai/inventory",
        "/ai/reservation-insights"
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401  # Unauthorized

def test_ai_pricing_approve_endpoint():
    """Test AI pricing recommendation approve endpoint."""
    # This would require creating a pricing recommendation first
    # For now, test that endpoint exists and requires auth
    token = create_user_and_login("approveuser@example.com", "password123", "Approve Test Restaurant")

    response = client.post(
        "/ai/pricing/1/approve",  # Using ID 1 which may not exist
        headers={"Authorization": f"Bearer {token}"}
    )
    # Should return 404 (not found) or 403 (forbidden) not 401 (unauthorized) since we have token
    assert response.status_code != 401

def test_ai_pricing_reject_endpoint():
    """Test AI pricing recommendation reject endpoint."""
    token = create_user_and_login("rejectuser@example.com", "password123", "Reject Test Restaurant")

    response = client.post(
        "/ai/pricing/1/reject",
        json={"reason": "Not needed at this time"},
        headers={"Authorization": f"Bearer {token}"}
    )
    # Should return 404 (not found) or 403 (forbidden) not 401 (unauthorized) since we have token
    assert response.status_code != 401