import pytest
from unittest.mock import patch
from app.services.data_service import data_service
from app.services.llm_service import llm_service


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure database is properly initialized and populated before tests execute."""
    data_service.initialize_database()


@pytest.fixture(autouse=True)
def mock_ollama_in_unit_tests(monkeypatch):
    """
    In accordance with assessment specifications, unit tests must NOT depend on an external
    Ollama instance or network availability. Mock is_ollama_available to False by default
    so tests execute deterministically in milliseconds using the certified fallback engine.
    """
    async def mock_is_available():
        return False

    monkeypatch.setattr(llm_service, "is_ollama_available", mock_is_available)
