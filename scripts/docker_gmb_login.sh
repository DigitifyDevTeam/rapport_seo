#!/usr/bin/env bash
# Alias for docker_gmb_prepare.sh (same interactive GMB login in Docker).
# Usage: ./scripts/docker_gmb_login.sh [origincbd|deepcleaning|digitify|cchabitat]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT}/scripts/docker_gmb_prepare.sh" "${1:-origincbd}"
