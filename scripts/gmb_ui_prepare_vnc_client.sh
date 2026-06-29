#!/usr/bin/env bash
# GMB prepare for one client on the VPS (noVNC). Opens Chrome in noVNC.
#
#   bash scripts/gmb_ui_prepare_vnc_client.sh deepcleaning   # login → gmb-deepcleaning.json
#   bash scripts/gmb_ui_prepare_vnc_client.sh digitify       # Performance URL only (browser opens)
#   bash scripts/gmb_ui_prepare_vnc_client.sh origincbd
#
# For monthly reports you need gmb-deepcleaning.json (run deepcleaning once) plus each
# client's gmb-performance-<client>.txt.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/gmb_vnc_common.sh
source "${ROOT}/scripts/gmb_vnc_common.sh"

CLIENT="${1:?Usage: $0 <client_id>  e.g. deepcleaning, digitify, origincbd}"
shift || true

case "${CLIENT}" in
  deepcleaning)
    gmb_vnc_warn_missing_master
    echo "Starting DeepCleaning login (saves gmb-deepcleaning.json)..."
    gmb_vnc_python scripts/gmb_ui_prepare_shared_account.py --clients deepcleaning "$@"
    ;;
  origincbd|digitify|guivarche)
    gmb_vnc_warn_missing_master
    echo "Opening browser for ${CLIENT} Performance URL..."
    gmb_vnc_python scripts/capture_gmb_performance_url.py "${CLIENT}" --show
    ;;
  *)
    echo "Unknown client: ${CLIENT}" >&2
    echo "Shared-account clients: deepcleaning, origincbd, digitify, guivarche" >&2
    echo "For cchabitat (separate Google account):" >&2
    echo "  bash scripts/gmb_vnc_shell.sh" >&2
    echo "  python scripts/clients/cchabitat/gmb_ui_prepare.py" >&2
    exit 1
    ;;
esac
