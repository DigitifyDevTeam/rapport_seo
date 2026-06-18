#!/usr/bin/env bash
# GMB sessions: prepare on Windows or VPS VNC (not headless cron).
#
# Same Google account (DeepCleaning, Origincbd, Digitify) — one login:
#
#   python scripts/gmb_ui_prepare_shared_account.py
#
# On VPS with noVNC:
#
#   ./scripts/gmb_ui_prepare_vnc.sh
#
# Then copy to outputs/_sessions/ on the server:
#   gmb-deepcleaning.json
#   gmb-performance-origincbd.txt
#   gmb-performance-digitify.txt
#
# Per-client only (separate account or dedicated session):
#   python scripts/clients/<client>/gmb_ui_prepare.py
#
set -euo pipefail
CLIENT="${1:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -z "${CLIENT}" ]]; then
  cat <<EOF
GMB prepare — shared Google account (recommended)

  python scripts/gmb_ui_prepare_shared_account.py

VPS VNC:

  ./scripts/gmb_ui_prepare_vnc.sh

Verify:

  python scripts/check_gmb_vps_sessions.py

Per-client prepare (only if needed):

  python scripts/clients/deepcleaning/gmb_ui_prepare.py
  python scripts/clients/origincbd/gmb_ui_prepare.py
  python scripts/clients/digitify/gmb_ui_prepare.py
EOF
  exit 0
fi

cat <<EOF
GMB prepare for "${CLIENT}"

If this client shares the agency Google account with DeepCleaning, use instead:

  python scripts/gmb_ui_prepare_shared_account.py

Dedicated prepare:

  python scripts/clients/${CLIENT}/gmb_ui_prepare.py

Copy to VPS: outputs/_sessions/gmb-${CLIENT}.json
             (or gmb-deepcleaning.json + gmb-performance-${CLIENT}.txt)

Verify: python scripts/check_gmb_vps_sessions.py
EOF
