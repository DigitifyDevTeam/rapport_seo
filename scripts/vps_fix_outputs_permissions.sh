#!/usr/bin/env bash
# Fix outputs/ + logs/ ownership via Docker (no host sudo).
#
# Root-owned files come from seo-vnc / old Docker runs. A one-shot container
# running as root can chown the bind-mounted outputs/ to your host uid.
#
#   bash scripts/vps_fix_outputs_permissions.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=docker_compose_user.sh
source "${ROOT}/scripts/docker_compose_user.sh"

OWNER="$(docker_host_user)"
MY_UID="$(docker_host_uid)"
echo "Fixing outputs/ and logs/ owner -> ${OWNER} (uid=${MY_UID}) via Docker"

_foreign_files() {
  find "${ROOT}/outputs" "${ROOT}/logs" ! -uid "${MY_UID}" 2>/dev/null || true
}

if ! _foreign_files | grep -q .; then
  chmod -R u+rwX "${ROOT}/outputs" "${ROOT}/logs" 2>/dev/null || true
  echo "Done (already owned by uid ${MY_UID})."
  exit 0
fi

echo "Foreign-owned paths (sample):"
_foreign_files | head -10

docker compose run --rm --no-TTY --user root --entrypoint "" seo-reports \
  chown -R "${OWNER}" /app/outputs /app/logs

docker compose run --rm --no-TTY --user root --entrypoint "" seo-reports \
  chmod -R u+rwX /app/outputs /app/logs

chmod -R u+rwX "${ROOT}/outputs" "${ROOT}/logs" 2>/dev/null || true

if _foreign_files | grep -q .; then
  echo "ERROR: some files are still not uid ${MY_UID}:" >&2
  _foreign_files | head -10 >&2
  exit 1
fi

echo "Done."
