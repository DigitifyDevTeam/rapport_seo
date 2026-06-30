#!/usr/bin/env bash
# Fix outputs/ + logs/ ownership (root or other UIDs from old Docker runs).
#
#   bash scripts/vps_fix_outputs_permissions.sh
#
# Requires sudo once when files are not owned by your user.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

OWNER="$(id -un):$(id -gn)"
MY_UID="$(id -u)"
echo "Setting owner of outputs/ and logs/ to ${OWNER} (uid=${MY_UID})"

_foreign_files() {
  find "${ROOT}/outputs" "${ROOT}/logs" ! -uid "${MY_UID}" 2>/dev/null || true
}

if _foreign_files | grep -q .; then
  echo "Foreign-owned files (not uid ${MY_UID}):"
  _foreign_files | head -15
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R "${OWNER}" "${ROOT}/outputs" "${ROOT}/logs"
    sudo chmod -R u+rwX "${ROOT}/outputs" "${ROOT}/logs"
  else
    echo "ERROR: cannot chown without sudo. Run as admin:" >&2
    echo "  sudo chown -R ${OWNER} ${ROOT}/outputs ${ROOT}/logs" >&2
    echo "  sudo chmod -R u+rwX ${ROOT}/outputs ${ROOT}/logs" >&2
    exit 1
  fi
else
  chmod -R u+rwX "${ROOT}/outputs" "${ROOT}/logs" 2>/dev/null || true
fi

echo "Done."
