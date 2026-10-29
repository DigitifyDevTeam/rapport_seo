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
  digitify) PROJECT_ID="k23l3ye7zj" ;;
  guivarche) PROJECT_ID="wck8kvahx2" ;;
  cchabitat) PROJECT_ID="" ;;
esac

gmb_vnc_ensure
mkdir -p "${ROOT}/outputs/_sessions" "${PROFILE}" 2>/dev/null || true

# Clarity noVNC login does not use Chrome profiles. Those folders are often
# owned by root and chmod on them fails. Only the session JSON must be writable.
shopt -s nullglob
for session_file in "${ROOT}/outputs/_sessions"/clarity-*.json; do
  if [[ -e "${session_file}" && ! -w "${session_file}" ]]; then
    rm -f "${session_file}" 2>/dev/null || true
  fi
done
shopt -u nullglob
if compgen -G "${ROOT}/outputs/_sessions/clarity-*.json" >/dev/null; then
  unwritable=0
  for session_file in "${ROOT}/outputs/_sessions"/clarity-*.json; do
    if [[ -e "${session_file}" && ! -w "${session_file}" ]]; then
      unwritable=1
    fi
  done
  if [[ "${unwritable}" -eq 1 ]]; then
    echo "Clarity JSON files are owned by another user. Fixing via container root..."
    docker compose --profile tools exec -T -u 0 seo-vnc \
      bash -lc 'chown '"$(id -u):$(id -g)"' /app/outputs/_sessions/clarity-*.json'
  fi
fi

echo "=== Clarity login for ${CLIENT} ==="
echo "1) Chrome opens in noVNC (ephemeral — no Chrome profile needed)."
echo "2) Sign in to Microsoft Clarity if asked."
echo "   *** TICK 'Rester connecté' / 'Keep me signed in' ***"
echo "   (without it the cookie is session-only and dies after one run)."
echo "3) Wait for the project dashboard + KPI cards."
echo "4) Press ENTER in this SSH terminal."
echo ""
echo "After a good login, install the keep-alive cron so the session does not"
echo "die between monthly reports:"
echo "  crontab -e"
echo "  15 4 */3 * * ${ROOT}/cron_clarity_keepalive.sh"
echo ""
echo "NOTE: all agency clients (deepcleaning/origincbd/digitify/guivarche/"
echo "cchabitat) share ONE Microsoft login — this re-login fixes all of them."
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
