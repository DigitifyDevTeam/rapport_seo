#!/usr/bin/env bash
# Start or restart noVNC for manual GMB / browser login on the VPS.
#
#   ./scripts/vnc_start.sh
#   bash scripts/vnc_start.sh    # if Permission denied after git pull
#
# Open: http://<vps-ip>:7900/vnc.html   password: vnc
# Or SSH tunnel (no extra firewall port): see ./scripts/vnc_open_firewall.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

chmod +x scripts/vnc_*.sh scripts/gmb_ui_prepare_vnc*.sh 2>/dev/null || true

echo "Building image if needed..."
docker compose build seo-reports

echo "Stopping old seo-vnc container (if any)..."
docker compose --profile tools stop seo-vnc 2>/dev/null || true
docker compose --profile tools rm -f seo-vnc 2>/dev/null || true

echo "Starting seo-vnc (noVNC on port 7900, host network)..."
if ! docker compose --profile tools up -d --force-recreate seo-vnc 2>&1; then
  echo ""
  echo "seo-vnc failed to start."
  echo "If you see 'iptables: No chain/target/match', pull latest code (host network fix)"
  echo "or ask your host admin to restart Docker: systemctl restart docker"
  exit 1
fi

sleep 8
if docker compose --profile tools ps seo-vnc 2>/dev/null | grep -q "Up"; then
  echo ""
  if bash "${ROOT}/scripts/vnc_health.sh"; then
    echo ""
    echo "noVNC is ready."
  else
    echo ""
    echo "Container is Up but noVNC is not reachable yet."
    echo "  docker compose --profile tools logs --tail 80 seo-vnc"
    echo "  ./scripts/vnc_open_firewall.sh"
    echo ""
    echo "SSH tunnel from your PC (no extra firewall port):"
    echo "  ssh -L 7900:127.0.0.1:7900 $(whoami)@$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "  Then open: http://localhost:7900/vnc.html"
    exit 1
  fi
  echo "  URL:      http://$(hostname -I 2>/dev/null | awk '{print $1}'):7900/vnc.html"
  echo "  Password: vnc"
  echo ""
  echo "If the URL fails from your PC, use SSH tunnel: ./scripts/vnc_open_firewall.sh"
  echo ""
  echo "Run GMB prepare (reuse DeepCleaning login):"
  echo "  ./scripts/gmb_ui_prepare_vnc_client.sh origincbd"
  echo "  ./scripts/gmb_ui_prepare_vnc_client.sh digitify"
  echo "  ./scripts/gmb_ui_prepare_vnc_client.sh guivarche"
  echo "  ./scripts/gmb_ui_prepare_vnc.sh --skip-master"
  echo ""
  echo "Logs: docker compose --profile tools logs -f seo-vnc"
else
  echo "seo-vnc failed to start. Check:"
  echo "  docker compose --profile tools logs seo-vnc"
  exit 1
fi
