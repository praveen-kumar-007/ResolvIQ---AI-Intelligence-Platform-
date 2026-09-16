#!/usr/bin/env python3
"""
Application Runner Script
Executes the FastAPI server using Uvicorn with auto-reload.
"""
import sys
import uvicorn

from app.core.config import get_settings


def main():
    settings = get_settings()
    print("=" * 66)
    print("  ResolvIQ - Enterprise AI Support Ticket Analytics System")
    print("  DOTMappers IT Pvt. Ltd. | End-to-End AI System Sprint")
    print("=" * 66)
    print(f" * Dashboard URL:    http://localhost:{settings.app_port}")
    print(f" * Swagger OpenAPI:  http://localhost:{settings.app_port}/docs")
    print(f" * Active Model:     {settings.llm_model} via {settings.ollama_base_url}")
    print(f" * Database Path:    {settings.database_path}")
    print("=" * 66)

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
