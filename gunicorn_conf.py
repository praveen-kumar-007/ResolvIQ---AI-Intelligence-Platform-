"""
Gunicorn Production Server Configuration
Usage:
    gunicorn -c gunicorn_conf.py app.main:app
"""
import multiprocessing
import os

# Server socket
bind = f"{os.getenv('APP_HOST', '0.0.0.0')}:{os.getenv('APP_PORT', '8000')}"
backlog = 2048

# Worker processes
# Standard calculation: 2 * num_cores + 1, or override via WORKERS env var
default_workers = max(2, multiprocessing.cpu_count() * 2 + 1)
workers = int(os.getenv("WORKERS", default_workers))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "60")) + 15
keepalive = 5

# Process naming
proc_name = "resolviq-production"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(L)ss)'

# Graceful restarts & limits
max_requests = 5000
max_requests_jitter = 500
graceful_timeout = 30
