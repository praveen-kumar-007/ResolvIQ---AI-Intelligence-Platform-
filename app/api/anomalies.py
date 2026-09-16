from typing import Optional
from fastapi import APIRouter, Query
from app.models.schemas import AnomalyListResponse, AnomalySummaryResponse
from app.services.anomaly_service import anomaly_service

router = APIRouter(tags=["Anomalies"])


@router.get("/anomalies", response_model=AnomalyListResponse)
def get_anomalies(
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium)"),
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly type"),
    priority: Optional[str] = Query(None, description="Filter by ticket priority"),
    category: Optional[str] = Query(None, description="Filter by ticket category"),
) -> AnomalyListResponse:
    """Retrieve detected anomalies across statistical resolution times, SLA breaches, response times, and customer ratings."""
    return anomaly_service.scan_anomalies(
        severity=severity,
        anomaly_type=anomaly_type,
        priority=priority,
        category=category,
    )


@router.get("/anomalies/summary", response_model=AnomalySummaryResponse)
def get_anomalies_summary() -> AnomalySummaryResponse:
    """Retrieve statistical summary breakdown of all current anomalies."""
    result = anomaly_service.scan_anomalies()
    return result.summary
