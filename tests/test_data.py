import pytest
from app.services.data_service import data_service, EXPECTED_COLUMNS


def test_data_ingestion_count():
    """Verify that CSV ingestion loads exactly 500 records into SQLite."""
    count = data_service.initialize_database(force_reload=True)
    assert count == 500
    assert data_service.get_total_count() == 500


def test_schema_columns():
    """Verify that all normalized column names are present in the table schema."""
    with data_service.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(support_tickets);")
        columns = [row["name"] for row in cursor.fetchall()]

    for expected in EXPECTED_COLUMNS:
        assert expected in columns


def test_null_preservation():
    """Verify that NULL values in resolution_time_hrs and customer_rating are not converted to 0."""
    with data_service.get_connection() as conn:
        cursor = conn.cursor()
        # Exactly 173 unresolved tickets should have NULL resolution_time_hrs and NULL customer_rating
        cursor.execute("SELECT COUNT(*) AS cnt FROM support_tickets WHERE status != 'Resolved' AND resolution_time_hrs IS NULL;")
        null_resol_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM support_tickets WHERE status != 'Resolved' AND customer_rating IS NULL;")
        null_rating_count = cursor.fetchone()["cnt"]

    assert null_resol_count == 173
    assert null_rating_count == 173


def test_ticket_retrieval():
    """Verify fetching individual tickets by ID."""
    tkt_1 = data_service.get_ticket_by_id("TKT-001")
    assert tkt_1["ticket_id"] == "TKT-001"
    assert tkt_1["category"] in ("Billing", "Technical", "General")
    assert tkt_1["status"] in ("Open", "Resolved", "Escalated")
    assert isinstance(tkt_1["response_time_hrs"], float)
