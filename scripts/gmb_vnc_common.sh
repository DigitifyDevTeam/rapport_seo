#!/usr/bin/env bash
# Shared helpers for GMB prepare inside seo-vnc / noVNC.
# Sourced by gmb_ui_prepare_vnc.sh and gmb_ui_prepare_vnc_client.sh — do not execute alone.
set -euo pipefail

: "${GMB_VNC_ROOT:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
GMB_VNC_DISPLAY="${VNC_DISPLAY:-:99}"
GMB_VNC_PROFILE="${SEO_REPORT_GMB_PROFILE:-/app/outputs/_sessions/chrome-profile-gmb-vps}"
GMB_VNC_MASTER="${GMB_VNC_ROOT}/outputs/_sessions/gmb-deepcleaning.json"

gmb_vnc_running() {
  docker compose --profile tools ps --status running seo-vnc 2>/dev/null \
    | grep -q "seo-vnc"
}

gmb_vnc_ensure() {
  cd "${GMB_VNC_ROOT}"
  if ! gmb_vnc_running; then
    echo "seo-vnc not running — starting noVNC..."
    bash "${GMB_VNC_ROOT}/scripts/vnc_start.sh"
  fi
  echo ""
  echo "Open noVNC in your browser (password: vnc):"
  echo "  http://<your-vps-ip>:7900/vnc.html"
  echo ""
  echo "VPS Chrome profile: ${GMB_VNC_PROFILE}"
  echo ""
  echo "Unlocking Chrome profiles..."
  docker compose --profile tools exec -T seo-vnc \
    bash /app/scripts/gmb_unlock_chrome_profiles.sh
  mkdir -p "${GMB_VNC_ROOT}/outputs/_sessions/chrome-profile-gmb-vps" 2>/dev/null || true
}

gmb_vnc_warn_missing_master() {
  if [[ ! -f "${GMB_VNC_MASTER}" ]]; then
    echo ""
    echo "Note: ${GMB_VNC_MASTER} is missing."
    echo "  Sign in in the browser window (same Google account for all clients)."
    echo "  For monthly reports, also run:"
    echo "    bash scripts/gmb_ui_prepare_vnc_client.sh deepcleaning"
    echo ""
  fi
}

gmb_vnc_python() {
  gmb_vnc_ensure
  docker compose --profile tools exec -it \
    -e DISPLAY="${GMB_VNC_DISPLAY}" \
    -e PYTHONPATH=/app \
    -e SEO_REPORT_VNC=1 \
    -e SEO_REPORT_GMB_PROFILE="${GMB_VNC_PROFILE}" \
    -e DBUS_SESSION_BUS_ADDRESS=/dev/null \
    -w /app \
    seo-vnc \
    python "$@"
}
