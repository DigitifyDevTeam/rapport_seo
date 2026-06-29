#!/usr/bin/env bash
# GMB prepare for one client on the VPS (noVNC). Opens Chrome in noVNC.
#
#   bash scripts/gmb_ui_prepare_vnc_client.sh deepcleaning
#   bash scripts/gmb_ui_prepare_vnc_client.sh digitify
#   bash scripts/gmb_ui_prepare_vnc_client.sh --fresh deepcleaning   # VPS IP changed
#
# After VPS IP change, run --fresh once, then deepcleaning, then other clients.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/gmb_vnc_common.sh
source "${ROOT}/scripts/gmb_vnc_common.sh"

FRESH=0
CLIENT=""
EXTRA_ARGS=()
for arg in "$@"; do
  case "${arg}" in
    --fresh)
      FRESH=1
      ;;
    *)
      if [[ -z "${CLIENT}" ]]; then
        CLIENT="${arg}"
      else
        EXTRA_ARGS+=("${arg}")
      fi
      ;;
  esac
done

CLIENT="${CLIENT:?Usage: $0 [--fresh] <client_id>  e.g. deepcleaning, digitify}"

if [[ "${FRESH}" -eq 1 ]]; then
  gmb_vnc_reset_sessions
  echo ""
fi

case "${CLIENT}" in
  deepcleaning)
    gmb_vnc_warn_missing_master
    echo "Starting DeepCleaning login (saves gmb-deepcleaning.json)..."
    gmb_vnc_python scripts/gmb_ui_prepare_shared_account.py --clients deepcleaning "${EXTRA_ARGS[@]}"
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
