#!/usr/bin/env bash
# Copy GMB session files into outputs/_sessions/ when SFTP cannot overwrite root-owned files.
#
# Shared Google account (DeepCleaning + Origincbd + Digitify):
#   Upload to HOME, then:
#     ./scripts/import_gmb_sessions.sh deepcleaning ~/gmb-deepcleaning.json
#     ./scripts/import_gmb_sessions.sh perf origincbd ~/gmb-performance-origincbd.txt
#     ./scripts/import_gmb_sessions.sh perf digitify ~/gmb-performance-digitify.txt
#
# Copy Origincbd login to Digitify (cookies only, not Origincbd KPIs):
#     ./scripts/import_gmb_sessions.sh auth digitify origincbd
#     ./scripts/bootstrap_gmb_digitify_from_origincbd.sh
#
# Do NOT import gmb-origincbd.json / gmb-digitify.json unless you need a dedicated session
# (those files block shared-session fallback). Remove stale copies on the VPS if present.
#
# Or copy several JSON sessions from one folder:
#     ./scripts/import_gmb_sessions.sh all ~/imports
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=docker_compose_user.sh
source "${ROOT}/scripts/docker_compose_user.sh"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
SESSIONS="${ROOT}/outputs/_sessions"
mkdir -p "${SESSIONS}"

import_perf_url() {
  local client="$1"
  local src="$2"
  local dest_name="gmb-performance-${client}.txt"
  local dest="${SESSIONS}/${dest_name}"

  if [[ ! -f "${src}" ]]; then
    echo "SKIP ${client}: file not found: ${src}" >&2
    return 1
  fi

  local src_dir
  src_dir="$(cd "$(dirname "${src}")" && pwd)"
  local src_base
  src_base="$(basename "${src}")"

  echo "Import ${src} -> outputs/_sessions/${dest_name}"
  docker compose run --rm --no-TTY --user 0:0 \
    -v "${src_dir}:/incoming:ro" \
    --entrypoint sh seo-reports -c "
      cp /incoming/${src_base} /app/outputs/_sessions/${dest_name}
      chown ${HOST_UID}:${HOST_GID} /app/outputs/_sessions/${dest_name}
      chmod 664 /app/outputs/_sessions/${dest_name}
    "
  docker compose run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
    python scripts/check_gmb_vps_sessions.py 2>/dev/null | grep -F "${client}:" || true
}

import_one() {
  local client="$1"
  local src="$2"
  local dest_name="gmb-${client}.json"
  local dest="${SESSIONS}/${dest_name}"

  if [[ ! -f "${src}" ]]; then
    echo "SKIP ${client}: file not found: ${src}" >&2
    return 1
  fi

  local src_dir
  src_dir="$(cd "$(dirname "${src}")" && pwd)"
  local src_base
  src_base="$(basename "${src}")"

  echo "Import ${src} -> outputs/_sessions/${dest_name}"
  docker compose run --rm --no-TTY --user 0:0 \
    -v "${src_dir}:/incoming:ro" \
    --entrypoint sh seo-reports -c "
      cp /incoming/${src_base} /app/outputs/_sessions/${dest_name}
      chown ${HOST_UID}:${HOST_GID} /app/outputs/_sessions/${dest_name}
      chmod 664 /app/outputs/_sessions/${dest_name}
    "
  docker compose run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
    python scripts/check_gmb_vps_sessions.py 2>/dev/null | grep -F "${client}:" || true
}

"${ROOT}/scripts/fix_outputs_perms.sh"

CLIENT="${1:-}"
SRC="${2:-}"

if [[ -z "${CLIENT}" ]]; then
  echo "Usage: $0 <client_id> <path-to-gmb-CLIENT.json>" >&2
  echo "   or: $0 perf <client_id> <path-to-gmb-performance-CLIENT.txt>" >&2
  echo "   or: $0 all <directory-with-gmb-*.json>" >&2
  exit 1
fi

if [[ "${CLIENT}" == "auth" ]]; then
  TARGET="${SRC:-}"
  SOURCE="${3:-}"
  if [[ -z "${TARGET}" || -z "${SOURCE}" ]]; then
    echo "Usage: $0 auth <target_client> <source_client>" >&2
    echo "Example: $0 auth digitify origincbd" >&2
    exit 1
  fi
  docker compose run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
    python scripts/gmb_copy_session_auth.py --from "${SOURCE}" --to "${TARGET}"
  exit 0
fi

if [[ "${CLIENT}" == "perf" ]]; then
  PERF_CLIENT="${SRC:-}"
  PERF_SRC="${3:-}"
  if [[ -z "${PERF_CLIENT}" ]]; then
    echo "Usage: $0 perf <client_id> <path-to-gmb-performance-CLIENT.txt>" >&2
    exit 1
  fi
  if [[ -z "${PERF_SRC}" ]]; then
    PERF_SRC="${HOME}/gmb-performance-${PERF_CLIENT}.txt"
  fi
  import_perf_url "${PERF_CLIENT}" "${PERF_SRC}"
  exit 0
fi

if [[ "${CLIENT}" == "all" ]]; then
  DIR="${SRC:-${HOME}/imports}"
  if [[ ! -d "${DIR}" ]]; then
    echo "Directory not found: ${DIR}" >&2
    exit 1
  fi
  shopt -s nullglob
  for f in "${DIR}"/gmb-*.json; do
    base="$(basename "${f}")"
    id="${base#gmb-}"
    id="${id%.json}"
    import_one "${id}" "${f}" || true
  done
  exit 0
fi

if [[ -z "${SRC}" ]]; then
  SRC="${HOME}/gmb-${CLIENT}.json"
fi

import_one "${CLIENT}" "${SRC}"
