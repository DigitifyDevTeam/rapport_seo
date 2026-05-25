#!/usr/bin/env bash
# Run one client report in Docker: ./scripts/docker_run_client.sh cchabitat 2026-04
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
CLIENT="${1:?client id}"
MONTH="${2:-}"
docker compose build seo-reports
ARGS=(python -m src.pipeline.run_monthly --client "${CLIENT}")
if [[ -n "${MONTH}" ]]; then
  ARGS+=(--month "${MONTH}")
fi
docker compose run --rm --no-TTY seo-reports "${ARGS[@]}"

# Reclaim outputs/ ownership for the host user so SFTP/scp can overwrite
# files on the next sync from a workstation (Docker writes as root).
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
docker compose run --rm --no-TTY --user 0:0 --entrypoint sh seo-reports -c "
  chown -R ${HOST_UID}:${HOST_GID} /app/outputs /app/logs 2>/dev/null || true
  chmod -R u+rwX,g+rX /app/outputs /app/logs 2>/dev/null || true
" >/dev/null 2>&1 || true
