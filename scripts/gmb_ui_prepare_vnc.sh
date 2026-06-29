#!/usr/bin/env bash
# GMB prepare in the VPS browser (noVNC). Reuses DeepCleaning login when using --skip-master.
#
#   bash scripts/gmb_ui_prepare_vnc.sh                              # all clients
#   bash scripts/gmb_ui_prepare_vnc.sh --clients deepcleaning
#   bash scripts/gmb_ui_prepare_vnc.sh --skip-master --clients digitify
#
# Per client (recommended):
#   bash scripts/gmb_ui_prepare_vnc_client.sh deepcleaning
#   bash scripts/gmb_ui_prepare_vnc_client.sh digitify
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/gmb_vnc_common.sh
source "${ROOT}/scripts/gmb_vnc_common.sh"

gmb_vnc_warn_missing_master
echo "Starting GMB prepare..."
gmb_vnc_python scripts/gmb_ui_prepare_shared_account.py "$@"
