# DPDP scanner API — Render / Docker production image
# Includes Chromium (Selenium) + WeasyPrint system libraries.
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    # WeasyPrint
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    # healthcheck
    curl \
    && rm -rf /var/lib/apt/lists/*

# Prefer system Chromium over webdriver-manager downloads
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV FLASK_ENV=production
ENV FLASK_DEBUG=0
# One worker: Selenium + in-memory rate limits are not multi-process safe
ENV GUNICORN_WORKERS=1
ENV GUNICORN_THREADS=4
ENV GUNICORN_TIMEOUT=600
ENV GUNICORN_MAX_REQUESTS=0
ENV PORT=5000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/results /data/uploads /data/jobs \
    && chmod -R 755 /data

# Render injects $PORT; gunicorn.conf.py binds 0.0.0.0:$PORT
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-5000}/health" || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
