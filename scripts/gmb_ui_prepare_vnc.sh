#!/usr/bin/env bash
# GMB prepare in the VPS browser (noVNC). Reuses DeepCleaning login when using --skip-master.
#
#   bash scripts/gmb_ui_prepare_vnc.sh
#   bash scripts/gmb_ui_prepare_vnc.sh --skip-master
#
# Manual shell (same as before):
#   bash scripts/gmb_vnc_shell.sh
#   python scripts/clients/deepcleaning/gmb_ui_prepare.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

VNC_DISPLAY="${VNC_DISPLAY:-:99}"
VPS_PROFILE="/app/outputs/_sessions/chrome-profile-gmb-vps"

_vnc_running() {
  docker compose --profile tools ps --status running seo-vnc 2>/dev/null \
    | grep -q "seo-vnc"
}

if ! _vnc_running; then
  echo "seo-vnc not running — starting noVNC..."
  bash "${ROOT}/scripts/vnc_start.sh"
fi

echo ""
echo "Open noVNC in your browser (password: vnc):"
echo "  http://<your-vps-ip>:7900/vnc.html"
echo ""
echo "VPS Chrome profile: ${VPS_PROFILE}"
echo ""
echo "Unlocking Chrome profiles..."
docker compose --profile tools exec -T seo-vnc \
  bash /app/scripts/gmb_unlock_chrome_profiles.sh
mkdir -p "${ROOT}/outputs/_sessions/chrome-profile-gmb-vps" 2>/dev/null || true

echo "Starting GMB prepare..."
docker compose --profile tools exec -it \
  -e DISPLAY="${VNC_DISPLAY}" \
  -e PYTHONPATH=/app \
  -e SEO_REPORT_VNC=1 \
  -e SEO_REPORT_GMB_PROFILE="${VPS_PROFILE}" \
  -e DBUS_SESSION_BUS_ADDRESS=/dev/null \
  -w /app \
  seo-vnc \
  python scripts/gmb_ui_prepare_shared_account.py "$@"
