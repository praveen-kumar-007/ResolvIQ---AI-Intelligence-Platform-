import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_api_stats():
    """Verify GET /stats returns complete operational metrics."""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()

    assert data["total_tickets"] == 500
    assert data["open_tickets"] == 111
    assert data["resolved_tickets"] == 327
    assert data["escalated_tickets"] == 62
    assert data["critical_tickets"] == 55
    assert data["average_response_time_hrs"] > 0
    assert data["average_resolution_time_hrs"] > 0
    assert data["average_customer_rating"] > 0


def test_api_query_count():
    """Verify POST /query with count question."""
    response = client.post("/query", json={"question": "How many tickets are currently open?"})
    assert response.status_code == 200
    data = response.json()

    assert data["query_type"] == "count"
    assert "111" in data["answer"]
    assert data["result"]["count"] == 111
    assert data["execution_time_ms"] >= 0


def test_api_query_avg_rating():
    """Verify POST /query for technical tickets average rating."""
    response = client.post("/query", json={"question": "What is the average customer rating for Technical tickets?"})
    assert response.status_code == 200
    data = response.json()

    assert data["query_type"] == "aggregate"
    assert "3.74" in data["answer"]
    assert data["result"]["value"] == 3.74


def test_api_anomalies():
    """Verify GET /anomalies and summary endpoint."""
    res_list = client.get("/anomalies")
    assert res_list.status_code == 200
    assert res_list.json()["total"] > 0

    res_summary = client.get("/anomalies/summary")
    assert res_summary.status_code == 200
    assert "by_type" in res_summary.json()


def test_api_tickets_pagination():
    """Verify GET /tickets pagination and filtering."""
    response = client.get("/tickets?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 500
    assert len(data["tickets"]) == 10
    assert data["page"] == 1


def test_api_ticket_by_id_success():
    """Verify GET /tickets/{ticket_id} for existing ticket."""
    response = client.get("/tickets/TKT-001")
    assert response.status_code == 200
    assert response.json()["ticket_id"] == "TKT-001"


def test_api_ticket_by_id_not_found():
    """Verify GET /tickets/{ticket_id} for non-existent ticket returns 404."""
    response = client.get("/tickets/TKT-9999")
    assert response.status_code == 404
    assert response.json()["error"] == "ResourceNotFoundError"
