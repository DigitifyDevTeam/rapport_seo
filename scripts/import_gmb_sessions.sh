#!/usr/bin/env bash
# Import GMB session JSON uploaded via SFTP without touching root-owned outputs/.
#
# FileZilla often gets "permission denied" on outputs/deepcleaning/2026-04/
# because Docker runs as root. Upload here instead (your home dir is writable):
#
#   ~/gmb_sessions_import/gmb-deepcleaning.json
#   ~/gmb_sessions_import/gmb-digitify.json
#
# Then on the VPS:
#   chmod +x scripts/import_gmb_sessions.sh
#   ./scripts/import_gmb_sessions.sh
#
# Optional: pass files as arguments:
#   ./scripts/import_gmb_sessions.sh ~/gmb_sessions_import/gmb-deepcleaning.json
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
IMPORT_DIR="${HOME}/gmb_sessions_import"
SESSIONS_DIR="${ROOT}/outputs/_sessions"
mkdir -p "${IMPORT_DIR}" "${SESSIONS_DIR}"

shopt -s nullglob
if [[ $# -gt 0 ]]; then
  FILES=("$@")
else
  FILES=("${IMPORT_DIR}"/gmb-*.json)
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "No session files found." >&2
  echo "Upload via FileZilla to: ${IMPORT_DIR}/" >&2
  echo "  gmb-deepcleaning.json" >&2
  echo "  gmb-digitify.json" >&2
  exit 1
fi

echo "Importing ${#FILES[@]} file(s) into ${SESSIONS_DIR} ..."

for src in "${FILES[@]}"; do
  if [[ ! -f "${src}" ]]; then
    echo "Skip (not found): ${src}" >&2
    continue
  fi
  base="$(basename "${src}")"
  dest="${SESSIONS_DIR}/${base}"
  echo "  ${src} -> ${dest}"
  docker compose run --rm --no-TTY --user 0:0 \
    -v "${src}:/import.json:ro" \
    --entrypoint sh seo-reports -c "
      cp /import.json /app/outputs/_sessions/${base}
      chown ${HOST_UID}:${HOST_GID} /app/outputs/_sessions/${base}
      chmod 664 /app/outputs/_sessions/${base}
    "
done

docker compose run --rm --no-TTY --user 0:0 --entrypoint sh seo-reports -c "
  chown -R ${HOST_UID}:${HOST_GID} /app/outputs/_sessions
  chmod -R u+rwX,g+rX /app/outputs/_sessions
" >/dev/null

echo ""
echo "Verifying sessions ..."
docker compose run --rm --no-TTY seo-reports python scripts/check_gmb_vps_sessions.py
