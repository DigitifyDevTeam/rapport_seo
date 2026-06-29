#!/usr/bin/env bash
# Start or restart noVNC for manual GMB / browser login on the VPS.
#
#   ./scripts/vnc_start.sh
#
# Open: http://<vps-ip>:7900/vnc.html   password: vnc
# Then in the xterm window (or SSH exec):
#   python scripts/gmb_ui_prepare_shared_account.py --skip-master
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "Building image if needed..."
docker compose build seo-reports

echo "Stopping old seo-vnc container (if any)..."
docker compose --profile tools stop seo-vnc 2>/dev/null || true
docker compose --profile tools rm -f seo-vnc 2>/dev/null || true

echo "Starting seo-vnc (noVNC on port 7900)..."
docker compose --profile tools up -d --no-recreate seo-vnc 2>/dev/null \
  || docker compose --profile tools up -d seo-vnc

sleep 3
if docker compose --profile tools ps seo-vnc 2>/dev/null | grep -q "Up"; then
  echo ""
  if bash "${ROOT}/scripts/vnc_health.sh"; then
    echo ""
    echo "noVNC is ready."
  else
    echo ""
    echo "Container is Up but noVNC is not reachable yet."
    echo "  docker compose --profile tools logs --tail 80 seo-vnc"
    echo "  sudo ./scripts/vnc_open_firewall.sh"
    echo ""
    echo "SSH tunnel workaround (from your PC):"
    echo "  ssh -L 7900:127.0.0.1:7900 $(whoami)@$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "  Then open: http://localhost:7900/vnc.html"
    exit 1
  fi
  echo "  URL:      http://$(hostname -I 2>/dev/null | awk '{print $1}'):7900/vnc.html"
  echo "  Password: vnc"
  echo ""
  echo "Run GMB prepare (reuse DeepCleaning login):"
  echo "  ./scripts/gmb_ui_prepare_vnc_client.sh origincbd"
  echo "  ./scripts/gmb_ui_prepare_vnc_client.sh digitify"
  echo "  ./scripts/gmb_ui_prepare_vnc.sh --skip-master"
  echo ""
  echo "Or manually:"
  echo "  docker compose --profile tools exec -it -e DISPLAY=:0 seo-vnc \\"
  echo "    python scripts/gmb_ui_prepare_shared_account.py --skip-master --clients origincbd"
  echo ""
  echo "Logs: docker compose --profile tools logs -f seo-vnc"
else
  echo "seo-vnc failed to start. Check:"
  echo "  docker compose --profile tools logs seo-vnc"
  exit 1
fi
