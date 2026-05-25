#!/usr/bin/env bash
# Reclaim ownership of outputs/ and logs/ for the host user.
#
# Docker writes report files as root (the Playwright image runs as root),
# which blocks SFTP/sshfs uploads, deletes, and overwrites for normal users.
# This script uses Docker itself (as root) to chown those volume-mounted
# folders back to the calling host user's UID/GID.
#
# Usage (on the VPS):
#     ./scripts/fix_outputs_perms.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

echo "Reclaiming outputs/ + logs/ for UID=${HOST_UID} GID=${HOST_GID} ..."
docker compose run --rm --no-TTY --user 0:0 --entrypoint sh seo-reports -c "
  mkdir -p /app/outputs/_sessions
  chown -R ${HOST_UID}:${HOST_GID} /app/outputs /app/logs 2>/dev/null || true
  chmod -R u+rwX,g+rwX,o+rX /app/outputs /app/logs 2>/dev/null || true
  echo 'OK'
"
mkdir -p "${ROOT}/outputs/_sessions" "${HOME}/gmb_sessions_import"
chmod 775 "${ROOT}/outputs" "${ROOT}/outputs/_sessions" 2>/dev/null || true
echo "Done."
echo "If FileZilla still denies writes under outputs/, upload sessions to:"
echo "  ${HOME}/gmb_sessions_import/"
echo "Then run: ./scripts/import_gmb_sessions.sh"
