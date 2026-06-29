#!/usr/bin/env bash
# GMB prepare in the VPS browser (noVNC). Reuses DeepCleaning login when using --skip-master.
#
#   bash scripts/gmb_ui_prepare_vnc.sh
#   bash scripts/gmb_ui_prepare_vnc.sh --skip-master
#
# Starts noVNC if needed → http://<vps-ip>:7900/vnc.html  password: vnc
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
echo "(Fresh Google login on the server — ignore Windows session cookies.)"
echo ""
echo "Unlocking Chrome profiles and starting GMB prepare..."
docker compose --profile tools exec -T seo-vnc \
  bash /app/scripts/gmb_unlock_chrome_profiles.sh
docker compose --profile tools exec -it \
  -e DISPLAY="${VNC_DISPLAY}" \
  -e SEO_REPORT_VNC=1 \
  -e SEO_REPORT_GMB_PROFILE="${VPS_PROFILE}" \
  -e DBUS_SESSION_BUS_ADDRESS=/dev/null \
  seo-vnc \
  python scripts/gmb_ui_prepare_shared_account.py "$@"
