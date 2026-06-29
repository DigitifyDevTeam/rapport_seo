# Playwright image includes Chromium system dependencies (fixes VPS libatk errors).
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SEO_REPORT_DOCKER=1 \
    SEO_REPORT_GMB_NO_PROFILE=1 \
    SEO_REPORT_BROWSER_CHANNEL=chromium \
    SEO_REPORT_EXPORT_PDF=false \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-venv \
    tesseract-ocr \
    tesseract-ocr-fra \
    nodejs \
    npm \
    xvfb \
    x11-utils \
    x11vnc \
    fluxbox \
    xterm \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt package.json package-lock.json ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install -r requirements.txt \
    && npm ci --omit=dev

COPY config ./config
COPY src ./src
COPY scripts ./scripts
COPY templates ./templates
COPY cron_monthly_reports.sh cron_docker_monthly_reports.sh docker-entrypoint.sh ./

RUN chmod +x /app/docker-entrypoint.sh /app/cron_monthly_reports.sh /app/cron_docker_monthly_reports.sh \
    /app/scripts/vnc_start.sh /app/scripts/vnc_server.sh /app/scripts/vnc_health.sh \
    /app/scripts/vnc_open_firewall.sh /app/scripts/gmb_ui_prepare_vnc.sh \
    /app/scripts/gmb_ui_prepare_vnc_client.sh /app/scripts/gmb_unlock_chrome_profiles.sh \
    /app/scripts/gmb_vnc_shell.sh /app/scripts/gmb_vnc_common.sh \
    /app/scripts/vps_report_preflight.sh \
    && mkdir -p /app/outputs /app/logs /app/secrets

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "src.pipeline.monthly_job"]
