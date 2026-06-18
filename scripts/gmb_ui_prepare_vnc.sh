#!/usr/bin/env bash
# One-time GMB login for DeepCleaning + Origincbd + Digitify (same Google account).
#
#   ./scripts/gmb_ui_prepare_vnc.sh
#
# Requires: docker compose profile tools (seo-vnc). Connect http://<vps>:7900 (password: vnc).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

docker compose --profile tools exec -e DISPLAY=:0 seo-vnc \
  python scripts/gmb_ui_prepare_shared_account.py "$@"
