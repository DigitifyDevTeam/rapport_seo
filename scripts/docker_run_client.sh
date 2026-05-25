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
