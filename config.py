"""Application configuration (environment variables + constants)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def is_production() -> bool:
    return (
        os.environ.get("RENDER", "").lower() == "true"
        or os.environ.get("FLASK_ENV", "").lower() == "production"
    )


def is_development() -> bool:
    return not is_production()


def get_secret_key() -> str:
    key = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if key:
        return key
    # Dev-only fallback — set FLASK_SECRET_KEY in production
    return secrets.token_hex(32)


# Paths
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR))).resolve()
RESULTS_DIR = DATA_DIR / "results"
JOBS_DIR = DATA_DIR / "jobs"
UPLOADS_DIR = DATA_DIR / "uploads"

# Ensure local data dirs exist (fresh clones / wiped disks).
for _path in (RESULTS_DIR, JOBS_DIR, UPLOADS_DIR):
    _path.mkdir(parents=True, exist_ok=True)

# Logging
LOG_FILE = Path(os.environ.get("LOG_FILE", str(BASE_DIR / "scanner.log")))
LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

# Server
PORT = int(os.environ.get("PORT", "5000"))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
API_KEY = os.environ.get("API_KEY", "").strip()

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

# Razorpay
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
RAZORPAY_PRO_PLAN_ID = os.environ.get("RAZORPAY_PRO_PLAN_ID", "").strip()

# Turnstile
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()

# LLM (optional)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()

# Quotas — Free + Pilot (legacy Pro kept for existing subscribers)
FREE_SCANS_PER_USER = int(os.environ.get("FREE_SCANS_PER_USER", "1"))
ANONYMOUS_FREE_SCANS = int(os.environ.get("ANONYMOUS_FREE_SCANS", "0"))
PRO_SCANS_PER_MONTH = int(os.environ.get("PRO_SCANS_PER_MONTH", "5"))
PILOT_SCANS_PER_DAY = int(os.environ.get("PILOT_SCANS_PER_DAY", "1"))

# Premium / one-time unlock
PREMIUM_ENABLED = os.environ.get("PREMIUM_ENABLED", "1") == "1"
PREMIUM_FREE_ACCESS = os.environ.get("PREMIUM_FREE_ACCESS", "0") == "1"
PREMIUM_PREVIEW_MISSING_INDICATORS = int(
    os.environ.get("PREMIUM_PREVIEW_MISSING_INDICATORS", "3")
)
PREMIUM_PRICE_PAISE = int(os.environ.get("PREMIUM_PRICE_PAISE", "29900"))  # ₹299
PREMIUM_CURRENCY = os.environ.get("PREMIUM_CURRENCY", "INR")
PREMIUM_COOKIE_NAME = os.environ.get("PREMIUM_COOKIE_NAME", "dpdp_premium")
PREMIUM_COOKIE_MAX_AGE = int(os.environ.get("PREMIUM_COOKIE_MAX_AGE", str(60 * 60 * 24 * 365)))
VISITOR_COOKIE_NAME = os.environ.get("VISITOR_COOKIE_NAME", "dpdp_visitor")

# Legacy Pro (disabled for new purchases — Pilot lives on TrustStack)
PRO_SUBSCRIPTION_ENABLED = os.environ.get("PRO_SUBSCRIPTION_ENABLED", "0") == "1"
PRO_PRICE_PAISE = int(os.environ.get("PRO_PRICE_PAISE", "99900"))
PRO_ORIGINAL_PRICE_PAISE = int(os.environ.get("PRO_ORIGINAL_PRICE_PAISE", "117500"))

# Report versioning
SCANNER_VERSION = os.environ.get("SCANNER_VERSION", "1.0.0")
RULES_VERSION = os.environ.get("RULES_VERSION", "DPDP Rules 2025 (Nov 2025 Gazette)")

# Scan limits
MAX_CONCURRENT_SCANS = int(os.environ.get("MAX_CONCURRENT_SCANS", "3"))
SCAN_TIMEOUT_SECONDS = int(os.environ.get("SCAN_TIMEOUT_SECONDS", "600"))
SCAN_JOB_TIMEOUT_SECONDS = int(os.environ.get("SCAN_JOB_TIMEOUT_SECONDS", "600"))

# Rate limiting
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "1") == "1"
RATE_LIMIT_SCANS_PER_HOUR = int(os.environ.get("RATE_LIMIT_SCANS_PER_HOUR", "10"))

# Gunicorn
GUNICORN_WORKERS = int(os.environ.get("GUNICORN_WORKERS", "1"))
GUNICORN_THREADS = int(os.environ.get("GUNICORN_THREADS", "4"))
GUNICORN_TIMEOUT = int(os.environ.get("GUNICORN_TIMEOUT", "300"))

# Webhooks / CORS
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
_cors_origins = os.environ.get("CORS_ORIGINS", "")
CORS_ORIGINS = (
    [o.strip() for o in _cors_origins.split(",") if o.strip()] if _cors_origins else []
)
