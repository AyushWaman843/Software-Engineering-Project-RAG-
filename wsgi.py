"""
WSGI entry point for production deployment (Gunicorn).

Usage:
    gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 wsgi:app
"""

from dotenv import load_dotenv

load_dotenv()

from app import app  # noqa: E402,F401
