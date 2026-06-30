#!/usr/bin/env bash
# One-time Clarity login on the VPS (noVNC). Saves session + Chrome profile.
#
#   bash scripts/clarity_ui_prepare_vnc_client.sh origincbd
#   bash scripts/clarity_ui_prepare_vnc_client.sh deepcleaning
#   bash scripts/clarity_ui_prepare_vnc_client.sh digitify
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/gmb_vnc_common.sh
source "${ROOT}/scripts/gmb_vnc_common.sh"

CLIENT="${1:?Usage: $0 <client_id>}"
case "${CLIENT}" in
  originecbd|origincbd) CLIENT="origincbd" ;;
esac

SESSION="${ROOT}/outputs/_sessions/clarity-${CLIENT}.json"
PROFILE="${ROOT}/outputs/_sessions/chrome-profile-clarity"
PROJECT_ID=""
case "${CLIENT}" in
  origincbd) PROJECT_ID="iqfjm1ewdj" ;;
  deepcleaning) PROJECT_ID="lfjtuxge3c" ;;
  digitify) PROJECT_ID="wck8kvahx2" ;;
  guivarche) PROJECT_ID="k23l3ye7zj" ;;
  cchabitat) PROJECT_ID="" ;;
esac

gmb_vnc_ensure
mkdir -p "${PROFILE}" 2>/dev/null || true

echo "=== Clarity login for ${CLIENT} ==="
echo "1) Chrome opens in noVNC."
echo "2) Sign in to Microsoft Clarity if asked."
echo "3) Wait for the project dashboard + KPI cards."
echo "4) Press ENTER in this SSH terminal."
echo ""
echo "Session file: ${SESSION}"
echo "Chrome profile: ${PROFILE}"
echo ""

if [[ -n "${PROJECT_ID}" ]]; then
  gmb_vnc_docker_exec python scripts/clarity_ui_login.py \
    --out "/app/outputs/_sessions/clarity-${CLIENT}.json" \
    --profile "/app/outputs/_sessions/chrome-profile-clarity" \
    --project-id "${PROJECT_ID}"
else
  gmb_vnc_docker_exec python scripts/clarity_ui_login.py \
    --out "/app/outputs/_sessions/clarity-${CLIENT}.json" \
    --profile "/app/outputs/_sessions/chrome-profile-clarity"
fi
