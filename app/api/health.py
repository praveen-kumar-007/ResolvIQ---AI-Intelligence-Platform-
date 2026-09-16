from fastapi import APIRouter
from app.core.config import get_settings
from app.models.schemas import HealthResponse
from app.services.data_service import data_service
from app.services.llm_service import llm_service

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Check health status of SQLite database, Ollama LLM service, and ticket data count."""
    settings = get_settings()

    # Database connectivity check
    try:
        total_tickets = data_service.get_total_count()
        db_status = "connected"
    except Exception:
        db_status = "error"
        total_tickets = 0

    # LLM provider and model telemetry check
    provider_info = await llm_service.get_active_provider_info()
    llm_status = "available" if provider_info["status"] == "connected" else "fallback_mode"

    overall_status = "healthy" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall_status,
        database=db_status,
        llm=llm_status,
        provider=provider_info["provider"],
        model=provider_info["model"],
        tickets_loaded=total_tickets
    )
