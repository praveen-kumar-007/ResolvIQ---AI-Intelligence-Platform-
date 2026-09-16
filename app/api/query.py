from fastapi import APIRouter, status
from app.models.schemas import QueryRequest, QueryResponse
from app.services.query_service import query_service

router = APIRouter(tags=["Query"])


@router.post("/query", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query_tickets(req: QueryRequest) -> QueryResponse:
    """Accept a natural language question, translate into a structured intent, execute deterministically, and return verified answers."""
    return await query_service.process_question(req)
