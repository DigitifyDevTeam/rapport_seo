#!/usr/bin/env bash
# How to reach noVNC without root on the VPS (no ufw/sudo on this host).
#
#   ./scripts/vnc_open_firewall.sh
#   ./scripts/vnc_open_firewall.sh --ip 197.5.129.6
#
# This script only prints instructions. Firewall changes need OVH Manager or SSH tunnel.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

_load_env() {
  if [[ -f "${ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT}/.env"
    set +a
  fi
  if [[ -f "${ROOT}/.env.server" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT}/.env.server"
    set +a
  fi
}

VNC_PORT="${VNC_PORT:-7900}"
ALLOW_IP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip) ALLOW_IP="${2:?--ip requires an address}"; shift 2 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

_load_env
if [[ -z "${ALLOW_IP}" ]]; then
  ALLOW_IP="${SSH_ALLOWED_IP_NEW:-${SSH_ALLOWED_IP_OLD:-197.5.129.6}}"
fi

SERVER_IP="${OVH_SERVER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

cat <<EOF
=== noVNC access (no root / no ufw on this server) ===

Recommended — SSH tunnel from your PC (uses port 22 only, keeps ${ALLOW_IP} safe):

  ssh -L ${VNC_PORT}:127.0.0.1:${VNC_PORT} \$(whoami)@${SERVER_IP}

Then open in your browser:

  http://localhost:${VNC_PORT}/vnc.html

Password: vnc

---

Alternative — open port ${VNC_PORT} in OVH Manager (no shell root needed):

  1. OVH Manager → your server → Network → Firewall
  2. Add rule: TCP ${VNC_PORT} from ${ALLOW_IP} only
  3. Keep existing SSH rule: TCP 22 from ${ALLOW_IP}
  4. Then open: http://${SERVER_IP}:${VNC_PORT}/vnc.html

---

Check noVNC inside Docker first:

  ./scripts/vnc_start.sh
  ./scripts/vnc_health.sh

EOF
