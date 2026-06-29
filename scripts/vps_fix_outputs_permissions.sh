#!/usr/bin/env bash
# Fix outputs/ files owned by root (old Docker runs) so report containers can write.
#
#   bash scripts/vps_fix_outputs_permissions.sh
#
# Requires sudo once if files are root-owned.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

OWNER="$(id -un):$(id -gn)"
echo "Setting owner of outputs/ and logs/ to ${OWNER}"

if find "${ROOT}/outputs" "${ROOT}/logs" -user root 2>/dev/null | grep -q .; then
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R "${OWNER}" "${ROOT}/outputs" "${ROOT}/logs"
  else
    echo "ERROR: root-owned files under outputs/ — run as admin:" >&2
    echo "  sudo chown -R ${OWNER} ${ROOT}/outputs ${ROOT}/logs" >&2
    find "${ROOT}/outputs" -user root 2>/dev/null | head -20
    exit 1
  fi
else
  chown -R "${OWNER}" "${ROOT}/outputs" "${ROOT}/logs" 2>/dev/null || true
fi

echo "Done."
