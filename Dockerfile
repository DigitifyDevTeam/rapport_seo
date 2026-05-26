# Playwright image includes Chromium system dependencies (fixes VPS libatk errors).
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache \
    XDG_CONFIG_HOME=/app/.config \
    MPLCONFIGDIR=/app/.cache/matplotlib \
    PUPPETEER_CACHE_DIR=/app/.cache/puppeteer \
    SEO_REPORT_DOCKER=1 \
    SEO_REPORT_GMB_NO_PROFILE=1 \
    SEO_REPORT_BROWSER_CHANNEL=chromium \
    SEO_REPORT_EXPORT_PDF=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fra \
    nodejs \
    npm \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt package.json package-lock.json ./
RUN pip install -r requirements.txt \
    && npm ci --omit=dev \
    && npx puppeteer browsers install chrome \
    && mkdir -p /app/.cache/matplotlib /app/.cache/puppeteer /app/.config \
    && chmod -R a+rwx /app/.cache /app/.config

COPY config ./config
COPY src ./src
COPY scripts ./scripts
COPY templates ./templates
COPY cron_monthly_reports.sh cron_docker_monthly_reports.sh docker-entrypoint.sh ./

RUN chmod +x /app/docker-entrypoint.sh /app/cron_monthly_reports.sh /app/cron_docker_monthly_reports.sh \
    && mkdir -p /app/outputs /app/logs /app/secrets

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "src.pipeline.monthly_job"]
