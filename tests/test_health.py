import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint_success():
    """Verify that /health reports connected database and valid ticket counts."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ("healthy", "degraded")
    assert data["database"] == "connected"
    assert data["tickets_loaded"] == 500
    assert "model" in data
    assert "llm" in data
    assert "provider" in data
