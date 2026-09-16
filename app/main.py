from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import anomalies, health, query, stats, tickets
from app.core.config import get_settings
from app.core.exceptions import AppBaseException, app_exception_handler
from app.core.logging_config import setup_logging
from app.services.data_service import data_service
from app.services.llm_service import llm_service

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database and verify runtime dependencies."""
    logger.info("Starting ResolvIQ — Enterprise AI Support Ticket Analytics System...")

    # Initialize data layer
    try:
        count = data_service.initialize_database()
        logger.info(f"Database operational with {count} verified tickets.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)

    # Verify LLM status
    ollama_ready = await llm_service.is_ollama_available()
    if ollama_ready:
        logger.info(f"Ollama connected successfully (Model: {settings.llm_model}).")
    else:
        logger.warning(
            f"Ollama not detected at {settings.ollama_base_url}. "
            "System will utilize high-precision deterministic fallback query translation."
        )

    yield

    logger.info("Application shutdown complete.")


app = FastAPI(
    title="ResolvIQ — Enterprise AI Support Ticket Analytics & Anomaly Intelligence",
    description=(
        "Enterprise-grade analytics engine translating natural language questions into safe, "
        "deterministic SQLite queries, coupled with multi-engine statistical anomaly detection for customer support operations."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized exception handler
app.add_exception_handler(AppBaseException, app_exception_handler)

# Include API Routers
app.include_router(health.router)
app.include_router(query.router)
app.include_router(anomalies.router)
app.include_router(stats.router)
app.include_router(tickets.router)

# Mount Static Files & Web Dashboard
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serve web dashboard UI."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "AI-Powered Customer Support Ticket Analytics System API is running. Visit /docs for Swagger UI."}
