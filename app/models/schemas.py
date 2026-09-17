from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check payload."""
    status: str = "healthy"
    database: str
    llm: str
    model: str
    tickets_loaded: int
    provider: Optional[str] = "ollama"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TicketResponse(BaseModel):
    """Normalized ticket record response."""
    ticket_id: str
    created_at: str
    category: str
    priority: str
    status: str
    response_time_hrs: float
    resolution_time_hrs: Optional[float] = None
    agent_id: str
    customer_rating: Optional[int] = None
    issue_summary: str


class TicketListResponse(BaseModel):
    """Paginated list of support tickets."""
    total: int
    page: int
    page_size: int
    tickets: List[TicketResponse]


class StatsResponse(BaseModel):
    """Dataset summary statistics."""
    total_tickets: int
    open_tickets: int
    resolved_tickets: int
    escalated_tickets: int
    critical_tickets: int
    high_priority_tickets: int
    medium_priority_tickets: int
    low_priority_tickets: int
    average_response_time_hrs: float
    average_resolution_time_hrs: Optional[float] = None
    average_customer_rating: Optional[float] = None
    anomaly_count: int


class AnomalyItem(BaseModel):
    """Single detected anomaly record."""
    ticket_id: str
    anomaly_type: str
    severity: str
    description: str
    relevant_value: Optional[float] = None
    threshold: Optional[float] = None
    created_at: str
    priority: str
    status: str
    agent_id: str
    category: Optional[str] = None


class AnomalySummaryResponse(BaseModel):
    """Aggregated anomaly counts by category and severity."""
    total_anomalies: int
    by_type: Dict[str, int]
    by_severity: Dict[str, int]
    by_priority: Dict[str, int]


class AnomalyListResponse(BaseModel):
    """List of anomalies with breakdown summary."""
    total: int
    summary: AnomalySummaryResponse
    anomalies: List[AnomalyItem]


class QueryRequest(BaseModel):
    """Natural language query request."""
    question: str = Field(..., min_length=2, description="Natural language question about tickets")


class QueryResponse(BaseModel):
    """Structured, data-backed query response."""
    question: str
    answer: str
    query_type: str
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    result: Any
    execution_time_ms: float
    is_ambiguous: bool = False
    is_chat_response: bool = False
    clarification: Optional[str] = None
    sql_executed: Optional[str] = None
    query_intent: Optional[Dict[str, Any]] = None

