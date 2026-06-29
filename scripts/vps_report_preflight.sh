#!/usr/bin/env bash
# Preflight before automated reports on the VPS (Path B — full server automation).
#
#   bash scripts/vps_report_preflight.sh
#   bash scripts/vps_report_preflight.sh digitify
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

CLIENT="${1:-}"

echo "=== 1) Stop noVNC (frees Chrome profile) ==="
docker compose --profile tools stop seo-vnc 2>/dev/null || true

echo ""
echo "=== 2) Unlock Chrome profiles ==="
bash "${ROOT}/scripts/gmb_unlock_chrome_profiles.sh"

echo ""
echo "=== 2b) outputs/ permissions (root-owned files break GMB write) ==="
bash "${ROOT}/scripts/vps_fix_outputs_permissions.sh" || true

echo ""
echo "=== 3) GMB sessions ==="
docker compose run --rm --no-TTY seo-reports python scripts/check_gmb_vps_sessions.py || true

echo ""
echo "=== 4) Network from report container (host network) ==="
for url in \
  "https://www.google.com" \
  "https://analytics.google.com" \
  "https://clarity.microsoft.com" \
  "https://business.google.com"
do
  printf "  %s ... " "${url}"
  if docker compose run --rm --no-TTY seo-reports \
    curl -fsS -o /dev/null -m 25 -w "%{http_code}" "${url}" 2>/dev/null | grep -qE '^[23]'; then
    echo "OK"
  else
    echo "FAIL (timeout or blocked — UI capture will fail)"
  fi
done

if [[ -n "${CLIENT}" ]]; then
  echo ""
  echo "=== 5) Quick GMB extract import test ==="
  docker compose run --rm --no-TTY seo-reports \
    python -c "import scripts.gmb_ui_extract; print('gmb_ui_extract imports: OK')"
fi

echo ""
echo "Done. If network OK and sessions OK, run:"
echo "  bash scripts/docker_run_client.sh <client> YYYY-MM"
echo "  bash cron_docker_run_all_clients.sh"
