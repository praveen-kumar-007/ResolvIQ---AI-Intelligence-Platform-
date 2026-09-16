from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.models.schemas import TicketListResponse, TicketResponse
from app.services.data_service import data_service

router = APIRouter(tags=["Tickets"])


@router.get("/tickets", response_model=TicketListResponse)
def list_tickets(
    category: Optional[str] = Query(None, description="Filter by category"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    status: Optional[str] = Query(None, description="Filter by status"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    search: Optional[str] = Query(None, description="Search ticket ID or issue summary"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
) -> TicketListResponse:
    """List support tickets with optional filtering, search, and pagination."""
    offset = (page - 1) * page_size
    items = data_service.get_tickets(
        category=category,
        priority=priority,
        status=status,
        agent_id=agent_id,
        search=search,
        limit=page_size,
        offset=offset
    )
    total = data_service.get_tickets_count(
        category=category,
        priority=priority,
        status=status,
        agent_id=agent_id,
        search=search
    )

    ticket_objs = [TicketResponse(**item) for item in items]

    return TicketListResponse(
        total=total,
        page=page,
        page_size=page_size,
        tickets=ticket_objs
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: str) -> TicketResponse:
    """Retrieve details for a single ticket by ticket ID."""
    ticket = data_service.get_ticket_by_id(ticket_id)
    return TicketResponse(**ticket)


@router.post("/reload", status_code=status.HTTP_200_OK)
def reload_data() -> dict:
    """Force re-ingestion of the CSV dataset into SQLite."""
    count = data_service.initialize_database(force_reload=True)
    return {"message": "Data reloaded successfully", "total_records": count}
