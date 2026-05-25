#!/usr/bin/env bash
# Save GMB session on the VPS (Playwright runs inside Docker, not host python3).
#
# Agency account (origincbd, digitify, deepcleaning): one login → gmb-origincbd.json
# CC Habitat: ./scripts/docker_gmb_prepare.sh cchabitat
#
# Usage:
#   ./scripts/docker_gmb_prepare.sh
#   ./scripts/docker_gmb_prepare.sh origincbd
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
CLIENT="${1:-origincbd}"

docker compose build seo-reports >/dev/null

SESSION_REL="$(docker compose run --rm --no-TTY seo-reports python -c "
from src.config import get_client, gmb_ui_session_owner, gmb_ui_session_path
c = get_client('${CLIENT}')
owner = gmb_ui_session_owner(c)
path = gmb_ui_session_path(c)
if owner != c.id:
    import sys
    print(f'Using shared session from {owner}', file=sys.stderr)
print('SESSION=' + path.as_posix())
" 2>&1 | grep '^SESSION=' | head -1 | cut -d= -f2- | tr -d '\r')"

if [[ -z "${SESSION_REL}" ]]; then
  echo "Could not resolve session path for client: ${CLIENT}" >&2
  exit 1
fi

mkdir -p outputs/_sessions

case "${CLIENT}" in
  origincbd)
    START_URL="https://www.google.com/search?hl=fr&q=Origine+CBD+Paris"
    ;;
  digitify)
    START_URL="https://www.google.com/search?hl=fr&q=Digitify"
    ;;
  deepcleaning)
    START_URL="https://www.google.com/search?hl=fr&q=Deep+Cleaning+Lavage+et+nettoyage+professionnel+Colombes"
    ;;
  cchabitat)
    START_URL="https://www.google.com/search?hl=fr&q=Concept+Confort+Habitat+couvreur+Val-de-Marne"
    ;;
  *)
    START_URL="https://business.google.com/locations"
    ;;
esac

echo "GMB session capture in Docker (client=${CLIENT})"
echo "Session file: ${SESSION_REL}"
echo ""
echo "1) A virtual browser opens (xvfb inside the container)."
echo "2) Complete Google sign-in + MFA if asked."
echo "3) Open Performance (#mpd= must appear in the URL)."
echo "4) Press ENTER in this terminal."
echo ""

# xvfb-run is bundled in the Playwright image for headed mode on Linux servers.
docker compose --profile tools run --rm -it \
  --entrypoint /app/docker-entrypoint.sh \
  seo-tools \
  xvfb-run -a python scripts/gmb_ui_login.py \
  --out "/app/${SESSION_REL}" \
  --start-url "${START_URL}" \
  --client-hint "${CLIENT}" \
  --channel chromium
