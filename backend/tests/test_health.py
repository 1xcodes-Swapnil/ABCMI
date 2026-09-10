"""
Tests for ABCI-MI Health Check and Diagnostic Endpoints
"""

from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    """Test that the root endpoint returns 200 and project metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "ABCI-MI Backend API"
    assert data["status"] == "running"
    assert "version" in data
    assert "health_check" in data


def test_health_ping(client: TestClient) -> None:
    """Test that the fast ping endpoint responds with pong."""
    response = client.get("/api/v1/health/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["ping"] == "pong"
    assert "timestamp" in data


def test_health_live(client: TestClient) -> None:
    """Test the liveness probe endpoint."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


def test_health_ready(client: TestClient) -> None:
    """Test the readiness probe endpoint."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "ready" in data
    assert "services_ready" in data


def test_full_health_endpoint(client: TestClient) -> None:
    """Test the comprehensive health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "project_name" in data
    assert "version" in data
    assert "uptime_seconds" in data
    assert "services" in data

    # Verify structured service health objects
    services = data["services"]
    assert "database" in services
    assert "redis" in services
    assert "qdrant" in services
    assert "storage" in services

    # Verify fields of individual services
    for service_name in ["database", "redis", "qdrant", "storage"]:
        service_info = services[service_name]
        assert "status" in service_info


def test_not_found_handling(client: TestClient) -> None:
    """Test global 404 error handler formatting."""
    response = client.get("/api/v1/non-existent-route")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
