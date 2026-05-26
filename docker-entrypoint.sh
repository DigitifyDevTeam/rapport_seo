#!/usr/bin/env bash
set -euo pipefail
cd /app
# Non-root ``docker compose run --user`` cannot write to /.cache or /.config
export HOME="${HOME:-/app}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/app/.cache}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/app/.config}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/app/.cache/matplotlib}"
export PUPPETEER_CACHE_DIR="${PUPPETEER_CACHE_DIR:-/app/.cache/puppeteer}"
mkdir -p "${MPLCONFIGDIR}" "${PUPPETEER_CACHE_DIR}" "${XDG_CONFIG_HOME}" 2>/dev/null || true
exec "$@"
