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
  echo "Chrome profile: ${GMB_VNC_PROFILE}"
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

gmb_vnc_docker_exec() {
  docker compose --profile tools exec -it \
    -u "$(id -u):$(id -g)" \
    -e DISPLAY="${GMB_VNC_DISPLAY}" \
    -e PYTHONPATH=/app \
    -e SEO_REPORT_VNC=1 \
    -e SEO_REPORT_GMB_PROFILE="${GMB_VNC_PROFILE}" \
    -w /app \
    seo-vnc \
    "$@"
}

gmb_vnc_python() {
  gmb_vnc_ensure
  gmb_vnc_docker_exec python "$@"
}

# Dedicated Chrome profile (e.g. cchabitat.seo@gmail.com — not the agency account).
gmb_vnc_python_profile() {
  local profile="${1:?profile path required}"
  shift
  GMB_VNC_PROFILE="${profile}"
  gmb_vnc_ensure
  gmb_vnc_docker_exec python "$@"
}

# After VPS IP change: backup agency sessions and reset shared VPS profile.
gmb_vnc_reset_sessions() {
  cd "${GMB_VNC_ROOT}"
  local backup sessions="${GMB_VNC_ROOT}/outputs/_sessions"
  backup="${sessions}/_vps_reset_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${backup}"
  echo "Backing up stale session files to ${backup}"
  shopt -s nullglob
  for f in "${sessions}"/gmb-*.json "${sessions}"/gmb-performance-*.txt; do
    if [[ -f "${f}" ]]; then
      mv "${f}" "${backup}/"
    fi
  done
  shopt -u nullglob
  if [[ -d "${sessions}/chrome-profile-gmb-vps" ]]; then
    mv "${sessions}/chrome-profile-gmb-vps" "${backup}/chrome-profile-gmb-vps"
  fi
  mkdir -p "${sessions}/chrome-profile-gmb-vps"
  echo "Fresh VPS profile ready."
}

# CC Habitat: separate Google account + often a Windows profile copy that crashes Chromium on Linux.
gmb_vnc_reset_cchabitat() {
  cd "${GMB_VNC_ROOT}"
  local backup sessions="${GMB_VNC_ROOT}/outputs/_sessions"
  backup="${sessions}/_cchabitat_reset_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${backup}"
  echo "Backing up CC Habitat session to ${backup}"
  if [[ -f "${sessions}/gmb-cchabitat.json" ]]; then
    mv "${sessions}/gmb-cchabitat.json" "${backup}/"
  fi
  if [[ -d "${sessions}/chrome-profile-gmb-cchabitat" ]]; then
    mv "${sessions}/chrome-profile-gmb-cchabitat" "${backup}/chrome-profile-gmb-cchabitat"
  fi
  mkdir -p "${sessions}/chrome-profile-gmb-cchabitat"
  echo "Fresh CC Habitat Chrome profile ready."
}
