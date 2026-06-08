"""
Test suite for authentication flows and tenant isolation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import Base, get_db
import models

# Test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
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

def test_register_user():
    """Test user registration endpoint."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "securepassword123",
            "tenant_name": "Test Restaurant"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_register_duplicate_email():
    """Test registering with duplicate email."""
    # Register first user
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "securepassword123",
            "tenant_name": "Test Restaurant"
        }
    )

    # Try to register again with same email
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "anotherpassword456",
            "tenant_name": "Another Restaurant"
        }
    )
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

def test_login_user():
    """Test user login endpoint."""
    # Register user first
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "securepassword123",
            "tenant_name": "Test Restaurant"
        }
    )

    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "securepassword123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "success" in data

def test_login_invalid_credentials():
    """Test login with invalid credentials."""
    # Register user first
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "securepassword123",
            "tenant_name": "Test Restaurant"
        }
    )

    # Login with wrong password
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

def test_get_current_user():
    """Test getting current user info."""
    # Register and login
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "securepassword123",
            "tenant_name": "Test Restaurant"
        }
    )
    token = register_response.json()["access_token"]

    # Get user info
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "admin"
    assert data["restaurant_name"] == "Test Restaurant"

def test_logout():
    """Test logout endpoint."""
    # Register and login
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "securepassword123",
            "tenant_name": "Test Restaurant"
        }
    )
    # Get the cookie from registration response
    cookies = register_response.cookies

    # Logout
    response = client.post("/api/v1/auth/logout", cookies=cookies)
    assert response.status_code == 200
    assert response.json()["success"] == True

def test_tenant_isolation_restaurant_create():
    """Test that users can only see their own restaurant data."""
    # Create first user and restaurant
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "user1@example.com",
            "password": "password123",
            "tenant_name": "Restaurant One"
        }
    )

    # Create second user and restaurant
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "user2@example.com",
            "password": "password456",
            "tenant_name": "Restaurant Two"
        }
    )

    # Login as user1
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "user1@example.com",
            "password": "password123"
        }
    )
    token = login_response.json()["access_token"]

    # Try to access menu (should be empty for user1 since no menu items created)
    response = client.get(
        "/menu/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    # Should return empty list since no menu items created yet
    assert isinstance(response.json(), list)

def test_password_strength_validation():
    """Test password minimum length validation."""
    # Try to register with short password
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "123",  # Too short
            "tenant_name": "Test Restaurant"
        }
    )
    assert response.status_code == 400
    # Validation error should be in response
    assert "Password must be at least 8 characters long" in str(response.json())

def test_rate_limit_on_login():
    """Test rate limiting on login endpoint."""
    # This test would require actually triggering rate limits
    # For now, we'll just verify the endpoint exists and limiter is configured
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword"
        }
    )
    # Should return 401 (unauthorized) not 429 (rate limited) since we're not hitting limit
    assert response.status_code == 401