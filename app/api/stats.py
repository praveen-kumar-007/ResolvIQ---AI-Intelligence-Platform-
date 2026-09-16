from fastapi import APIRouter
from app.models.schemas import StatsResponse
from app.services.anomaly_service import anomaly_service
from app.services.data_service import data_service

router = APIRouter(tags=["Statistics"])


@router.get("/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    """Retrieve operational metrics, volume distribution, response benchmarks, and anomaly metrics."""
    with data_service.get_connection() as conn:
        cursor = conn.cursor()

        # Ticket counts by status
        cursor.execute("SELECT status, COUNT(*) AS cnt FROM support_tickets GROUP BY status;")
        status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}

        # Ticket counts by priority
        cursor.execute("SELECT priority, COUNT(*) AS cnt FROM support_tickets GROUP BY priority;")
        priority_counts = {row["priority"]: row["cnt"] for row in cursor.fetchall()}

        # Averages
        cursor.execute("""
            SELECT
                COUNT(*) AS total_count,
                AVG(response_time_hrs) AS avg_resp,
                AVG(resolution_time_hrs) AS avg_resol,
                AVG(customer_rating) AS avg_rating
            FROM support_tickets;
        """)
        row = cursor.fetchone()

        total = row["total_count"]
        avg_resp = round(float(row["avg_resp"]), 2) if row["avg_resp"] is not None else 0.0
        avg_resol = round(float(row["avg_resol"]), 2) if row["avg_resol"] is not None else None
        avg_rating = round(float(row["avg_rating"]), 2) if row["avg_rating"] is not None else None

    # Anomaly count
    anomalies_res = anomaly_service.scan_anomalies()
    anomaly_count = anomalies_res.total

    return StatsResponse(
        total_tickets=total,
        open_tickets=status_counts.get("Open", 0),
        resolved_tickets=status_counts.get("Resolved", 0),
        escalated_tickets=status_counts.get("Escalated", 0),
        critical_tickets=priority_counts.get("Critical", 0),
        high_priority_tickets=priority_counts.get("High", 0),
        medium_priority_tickets=priority_counts.get("Medium", 0),
        low_priority_tickets=priority_counts.get("Low", 0),
        average_response_time_hrs=avg_resp,
        average_resolution_time_hrs=avg_resol,
        average_customer_rating=avg_rating,
        anomaly_count=anomaly_count
    )
