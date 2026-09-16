# ==============================================================================
# ResolvIQ - Enterprise AI Support Ticket Analytics Platform
# Production Dockerfile
# ==============================================================================
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_PATH=/app/data/support_tickets.db \
    CSV_PATH=/app/data/support_tickets.csv

# Install runtime dependencies for healthchecks and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create non-root system user and group for security
RUN groupadd -g 10001 resolviq && \
    useradd -u 10001 -g resolviq -m -s /bin/bash resolviq

# Install Python dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and configuration
COPY app/ ./app/
COPY api/ ./api/
COPY data/ ./data/
COPY run.py gunicorn_conf.py vercel.json ./

# Ensure correct permissions for non-root user
RUN chown -R resolviq:resolviq /app && \
    chmod -R 755 /app

# Switch to non-root user
USER resolviq

# Expose FastAPI application port
EXPOSE 8000

# Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
