#!/usr/bin/env bash
# GMB prepare in the VPS browser (noVNC). Reuses DeepCleaning login when using --skip-master.
#
#   ./scripts/gmb_ui_prepare_vnc.sh
#   ./scripts/gmb_ui_prepare_vnc.sh --skip-master
#
# Starts noVNC if needed → http://<vps-ip>:7900/vnc.html  password: vnc
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

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
echo "Starting GMB prepare inside the container (interactive)..."
docker compose --profile tools exec -it -e DISPLAY=:0 seo-vnc \
  python scripts/gmb_ui_prepare_shared_account.py "$@"
