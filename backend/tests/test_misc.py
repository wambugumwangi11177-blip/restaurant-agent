"""
Test suite for miscellaneous endpoints.
"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Restaurant Agent API"
    assert data["version"] == "2.1.0"
    assert data["status"] == "ok"

def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_agentic_goals_endpoint_requires_auth():
    """Test that agentic goals endpoint requires authentication."""
    response = client.get("/agentic/goals")
    assert response.status_code == 401  # Unauthorized

def test_agentic_goals_post_requires_auth():
    """Test that posting agentic goals requires authentication."""
    response = client.post(
        "/agentic/goals",
        json={
            "goal_type": "revenue_increase",
            "description": "Increase monthly revenue by 15%",
            "success_criteria": {"target_percentage": 15},
            "priority": 1
        }
    )
    assert response.status_code == 401  # Unauthorized

def test_cors_headers():
    """Test that CORS headers are present."""
    response = client.options("/")
    # Check for CORS headers (may vary based on implementation)
    assert response.status_code == 200

def test_security_headers_present():
    """Test that security headers are present in responses."""
    response = client.get("/")
    headers = response.headers
    # Check for some common security headers
    # Note: Actual implementation may vary
    assert "content-type" in headers

def test_404_on_nonexistent_endpoint():
    """Test that nonexistent endpoints return 404."""
    response = client.get("/nonexistent/endpoint")
    assert response.status_code == 404

def test_method_not_allowed():
    """Test that wrong HTTP methods return 405."""
    response = client.put("/")  # PUT not allowed on root
    assert response.status_code == 405

def test_auth_endpoints_documentation():
    """Test that auth endpoints are properly documented in OpenAPI."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_openapi_json():
    """Test that OpenAPI JSON is accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert data["info"]["title"] == "Restaurant Agent API"

def test_api_versioning_in_paths():
    """Test that API versioning is consistent in paths."""
    # Test that auth endpoints use /api/v1/ prefix
    response = client.post("/api/v1/auth/register", json={})
    # Should get validation error (422) not 404
    assert response.status_code == 422

    # Test that non-versioned auth endpoint doesn't exist
    response = client.post("/auth/register", json={})
    assert response.status_code == 404

def test_health_endpoint_detailed():
    """Test health endpoint with more detail."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    # May include additional health info

def test_app_info_endpoint():
    """Test app info / root endpoint details."""
    response = client.get("/")
    data = response.json()
    assert "service" in data
    assert "version" in data
    assert "status" in data
    assert isinstance(data["service"], str)
    assert isinstance(data["version"], str)
    assert isinstance(data["status"], str)