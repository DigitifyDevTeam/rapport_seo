#!/usr/bin/env bash
# Remove Chromium profile locks under outputs/_sessions/ (Windows → VPS copy).
#
#   bash scripts/gmb_unlock_chrome_profiles.sh
#   docker compose --profile tools exec -T seo-vnc bash /app/scripts/gmb_unlock_chrome_profiles.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSIONS="${ROOT}/outputs/_sessions"

_unlock_dir() {
  local dir="$1"
  [[ -d "${dir}" ]] || return 0
  rm -f "${dir}/SingletonLock" "${dir}/SingletonCookie" "${dir}/SingletonSocket" 2>/dev/null || true
  rm -f "${dir}/Default/LOCK" "${dir}/Default/lockfile" 2>/dev/null || true
  echo "Unlocked: ${dir}"
}

shopt -s nullglob
for dir in "${SESSIONS}"/chrome-profile-gmb* "${SESSIONS}"/chrome-profile "${SESSIONS}"/chrome-profile-gmb-vps; do
  _unlock_dir "${dir}"
done

pkill -f 'chrome-linux/chrome.*chrome-profile-gmb' 2>/dev/null || true
echo "Done."
