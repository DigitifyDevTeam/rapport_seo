#!/usr/bin/env bash
# GMB prepare for one client on the VPS (noVNC + shared Google account).
#
# Order matters for origincbd / digitify (same Google account as deepcleaning):
#   1) bash scripts/gmb_ui_prepare_vnc_client.sh deepcleaning   # login once → gmb-deepcleaning.json
#   2) bash scripts/gmb_ui_prepare_vnc_client.sh origincbd      # Performance URL only
#   3) bash scripts/gmb_ui_prepare_vnc_client.sh digitify       # Performance URL only
#
# Equivalent (inside docker, same env as gmb_ui_prepare_vnc.sh):
#   bash scripts/gmb_ui_prepare_vnc.sh --clients deepcleaning
#   bash scripts/gmb_ui_prepare_vnc.sh --skip-master --clients digitify
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

CLIENT="${1:?Usage: $0 <client_id>  e.g. origincbd}"
shift || true

case "${CLIENT}" in
  deepcleaning)
  exec bash "${ROOT}/scripts/gmb_ui_prepare_vnc.sh" --clients deepcleaning "$@"
    ;;
  origincbd|digitify)
  exec bash "${ROOT}/scripts/gmb_ui_prepare_vnc.sh" \
    --skip-master --clients "${CLIENT}" "$@"
    ;;
  *)
    echo "Unknown client: ${CLIENT}" >&2
    echo "Shared-account clients: deepcleaning, origincbd, digitify" >&2
    echo "For cchabitat (separate Google account):" >&2
    echo "  ./scripts/vnc_start.sh" >&2
    echo "  docker compose --profile tools exec -it -e DISPLAY=:99 -e PYTHONPATH=/app seo-vnc \\" >&2
    echo "    python scripts/clients/cchabitat/gmb_ui_prepare.py" >&2
    exit 1
    ;;
esac
