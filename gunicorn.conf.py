"""Gunicorn configuration for production API deployment (Render / Docker)."""

import os

from config import GUNICORN_THREADS, GUNICORN_TIMEOUT, GUNICORN_WORKERS

# Render injects PORT at runtime — re-read here so bind is always correct.
_port = int(os.getenv("PORT", "5000"))
bind = f"0.0.0.0:{_port}"
workers = GUNICORN_WORKERS
threads = GUNICORN_THREADS
worker_class = "gthread"
timeout = GUNICORN_TIMEOUT
keepalive = 5
accesslog = "-"
errorlog = "-"
capture_output = True
# Default 0 — worker recycle mid-scan kills background Selenium threads and surfaces
# "Scan interrupted by server restart" to clients. Set GUNICORN_MAX_REQUESTS>0 only
# if scans run out-of-process.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "0"))
prefetch_factor = 1
