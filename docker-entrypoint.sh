#!/usr/bin/env bash
set -euo pipefail
cd /app
# Non-root ``docker compose run --user`` cannot reliably write under /app
# (bind-mounted repo may be root-owned). Prefer /tmp which is writable.
export HOME="${HOME:-/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/.cache}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/tmp/.config}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/.cache/matplotlib}"
export PUPPETEER_CACHE_DIR="${PUPPETEER_CACHE_DIR:-/tmp/.cache/puppeteer}"
mkdir -p "${MPLCONFIGDIR}" "${PUPPETEER_CACHE_DIR}" "${XDG_CONFIG_HOME}" 2>/dev/null || true
exec "$@"
