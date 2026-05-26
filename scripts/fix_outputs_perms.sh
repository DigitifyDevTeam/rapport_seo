#!/usr/bin/env bash
# Reclaim ownership of outputs/ (especially outputs/_sessions/) for the SFTP user.
#
# Run BEFORE FileZilla upload if you get "permission denied":
#     ./scripts/fix_outputs_perms.sh
#
# Or upload session files to your HOME, then:
#     ./scripts/import_gmb_sessions.sh deepcleaning ~/gmb-deepcleaning.json
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

echo "Reclaiming outputs/ + logs/ for UID=${HOST_UID} GID=${HOST_GID} (${USER:-user}) ..."
mkdir -p "${ROOT}/outputs/_sessions" "${ROOT}/logs"

docker compose build seo-reports >/dev/null 2>&1 || true

docker compose run --rm --no-TTY --user 0:0 --entrypoint sh seo-reports -c "
  mkdir -p /app/outputs/_sessions /app/logs
  chown -R ${HOST_UID}:${HOST_GID} /app/outputs /app/logs
  find /app/outputs -type d -exec chmod 775 {} +
  find /app/outputs -type f -exec chmod 664 {} +
  find /app/logs -type d -exec chmod 775 {} + 2>/dev/null || true
  find /app/logs -type f -exec chmod 664 {} + 2>/dev/null || true
  ls -la /app/outputs/_sessions | head -20
  echo OK
"

echo ""
echo "Done. You can now:"
echo "  - Upload via FileZilla to outputs/_sessions/ and outputs/<client>/<month>/"
echo "  - Or: ./scripts/import_gmb_sessions.sh <client> ~/gmb-<client>.json"
echo ""
