#!/usr/bin/env bash
# Interactive shell inside seo-vnc (same env as manual GMB prepare).
#
#   bash scripts/gmb_vnc_shell.sh
#
# Then inside the container:
#   python scripts/clients/deepcleaning/gmb_ui_prepare.py
#   python scripts/gmb_ui_prepare_shared_account.py
#   python scripts/capture_gmb_performance_url.py origincbd --show
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

VNC_DISPLAY="${VNC_DISPLAY:-:99}"
VPS_PROFILE="${SEO_REPORT_GMB_PROFILE:-/app/outputs/_sessions/chrome-profile-gmb-vps}"

if ! docker compose --profile tools ps --status running seo-vnc 2>/dev/null | grep -q "seo-vnc"; then
  bash "${ROOT}/scripts/vnc_start.sh"
fi

docker compose --profile tools exec -it \
  -e DISPLAY="${VNC_DISPLAY}" \
  -e PYTHONPATH=/app \
  -e SEO_REPORT_VNC=1 \
  -e SEO_REPORT_GMB_PROFILE="${VPS_PROFILE}" \
  -e DBUS_SESSION_BUS_ADDRESS=/dev/null \
  seo-vnc \
  bash
