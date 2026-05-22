# Playwright image includes Chromium system dependencies (fixes VPS libatk errors).
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SEO_REPORT_GMB_NO_PROFILE=1 \
    SEO_REPORT_BROWSER_CHANNEL=chromium \
    SEO_REPORT_EXPORT_PDF=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fra \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt package.json package-lock.json ./
RUN pip install -r requirements.txt \
    && npm ci --omit=dev

COPY config ./config
COPY src ./src
COPY scripts ./scripts
COPY templates ./templates
COPY cron_monthly_reports.sh cron_docker_monthly_reports.sh docker-entrypoint.sh ./

RUN chmod +x /app/docker-entrypoint.sh /app/cron_monthly_reports.sh /app/cron_docker_monthly_reports.sh \
    && mkdir -p /app/outputs /app/logs /app/secrets

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "src.pipeline.monthly_job"]
