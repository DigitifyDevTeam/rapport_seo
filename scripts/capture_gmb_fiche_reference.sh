#!/usr/bin/env bash
# Capture public GBP fiche (knowledge panel) for use as business_card_reference.
#
#   bash scripts/capture_gmb_fiche_reference.sh origincbd
#
# Requires seo-vnc running. Opens Chrome in noVNC (--show).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/gmb_vnc_common.sh
source "${ROOT}/scripts/gmb_vnc_common.sh"

CLIENT="${1:?Usage: $0 <client_id>}"
gmb_vnc_python scripts/capture_gmb_fiche_reference.py "${CLIENT}" --show
