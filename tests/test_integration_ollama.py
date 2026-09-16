import pytest
import httpx
from app.core.config import get_settings
from app.models.query_models import QueryIntent
from app.services.llm_service import LLMService


@pytest.mark.asyncio
async def test_live_ollama_integration():
    """Live integration test testing query parsing pipeline against Ollama with fallback resilience."""
    settings = get_settings()
    llm_svc = LLMService()

    # Direct live check
    is_live = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{settings.ollama_base_url}/api/tags")
            is_live = (res.status_code == 200)
    except Exception:
        is_live = False

    if not is_live:
        pytest.skip(f"Ollama server not active at {settings.ollama_base_url}; skipping live integration test.")

    # Execute resilient query parsing
    intent = await llm_svc.parse_query("How many critical tickets are currently open?")
    assert intent is not None
    assert isinstance(intent, QueryIntent)
    assert intent.operation.value in ("count", "filter_list")
