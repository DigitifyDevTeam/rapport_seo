#!/usr/bin/env bash
# Run keyword-compare-only report (SimpleSERP custom date range) in Docker:
#   bash scripts/docker_run_keyword_compare.sh guivarche 01/08/2026 01/09/2026
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=docker_compose_user.sh
source "${ROOT}/scripts/docker_compose_user.sh"

CLIENT="${1:?client id (e.g. guivarche)}"
FROM_DATE="${2:?from date DD/MM/YYYY}"
TO_DATE="${3:?to date DD/MM/YYYY}"
shift 3
EXTRA_ARGS=("$@")

bash "${ROOT}/scripts/vps_fix_outputs_permissions.sh"
docker compose build seo-reports
docker compose run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
  python scripts/build_template.py --force

ARGS=(
  python scripts/run_keyword_compare_only.py
  --client "${CLIENT}"
  --from-date "${FROM_DATE}"
  --to-date "${TO_DATE}"
)
if ((${#EXTRA_ARGS[@]})); then
  ARGS+=("${EXTRA_ARGS[@]}")
fi
docker compose run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports "${ARGS[@]}"
