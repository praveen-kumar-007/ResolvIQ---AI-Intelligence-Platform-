#!/usr/bin/env python3
"""
Application Runner Script
Executes the FastAPI server with production or development configurations.
"""
import argparse
import sys
import uvicorn

from app.core.config import get_settings


def parse_args():
    parser = argparse.ArgumentParser(description="Run the ResolvIQ FastAPI server.")
    parser.add_argument(
        "--prod", "--production",
        action="store_true",
        dest="production",
        help="Run in production mode (disables reload, enables multi-worker concurrency)."
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host interface to bind (default from config)."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port number to bind (default from config)."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes in production mode."
    )
    return parser.parse_known_args()[0]


def main():
    args = parse_args()
    settings = get_settings()

    is_prod = args.production or settings.is_production
    host = args.host or settings.app_host
    port = args.port or settings.app_port
    workers = args.workers or (settings.workers if is_prod else 1)
    reload = not is_prod

    mode_label = "PRODUCTION" if is_prod else "DEVELOPMENT (Auto-Reload)"

    print("=" * 66)
    print(f"  ResolvIQ - Enterprise AI Support Ticket Analytics System [{mode_label}]")
    print("  DOTMappers IT Pvt. Ltd. | End-to-End AI System Sprint")
    print("=" * 66)
    print(f" * Dashboard URL:    http://localhost:{port}")
    if settings.docs_enabled:
        print(f" * Swagger OpenAPI:  http://localhost:{port}/docs")
    print(f" * Active Model:     {settings.llm_model} via {settings.ollama_base_url}")
    print(f" * Database Path:    {settings.database_path}")
    print(f" * Worker Count:     {workers}")
    print(f" * Environment:      {settings.environment}")
    print("=" * 66)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else None,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
