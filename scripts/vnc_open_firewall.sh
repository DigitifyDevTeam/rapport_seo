#!/usr/bin/env bash
# Open noVNC port (7900) on the OVH VPS firewall.
#
#   sudo ./scripts/vnc_open_firewall.sh
#   sudo ./scripts/vnc_open_firewall.sh --ip 197.5.129.6   # office IP only (safer)
#
# Also check OVH Manager → Bare Metal / VPS → Network → Firewall if the port stays blocked.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo $0 $*" >&2
  exit 1
fi

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

_log() { echo "[vnc-fw] $*"; }

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
  ALLOW_IP="${SSH_ALLOWED_IP_NEW:-${SSH_ALLOWED_IP_OLD:-}}"
fi

if command -v ufw >/dev/null 2>&1; then
  if [[ -n "${ALLOW_IP}" ]]; then
    if ufw status 2>/dev/null | grep -qF "${ALLOW_IP}"; then
      _log "ufw: rule for ${ALLOW_IP} may already exist"
    fi
    ufw allow from "${ALLOW_IP}" to any port "${VNC_PORT}" proto tcp \
      comment "rapport_seo noVNC"
    _log "ufw: allowed ${ALLOW_IP} -> tcp/${VNC_PORT}"
  else
    ufw allow "${VNC_PORT}"/tcp comment "rapport_seo noVNC"
    _log "ufw: allowed tcp/${VNC_PORT} from anywhere (use --ip for restrict)"
  fi
  ufw reload 2>/dev/null || true
  ufw status | grep -E "Status:|${VNC_PORT}" || ufw status
else
  _log "ufw not found — opening with iptables"
  if [[ -n "${ALLOW_IP}" ]]; then
    iptables -C INPUT -s "${ALLOW_IP}" -p tcp --dport "${VNC_PORT}" -j ACCEPT 2>/dev/null \
      || iptables -I INPUT -s "${ALLOW_IP}" -p tcp --dport "${VNC_PORT}" -j ACCEPT
  else
    iptables -C INPUT -p tcp --dport "${VNC_PORT}" -j ACCEPT 2>/dev/null \
      || iptables -I INPUT -p tcp --dport "${VNC_PORT}" -j ACCEPT
  fi
  _log "Persist: apt install iptables-persistent && netfilter-persistent save"
fi

_log "Done. Test: ./scripts/vnc_health.sh"
_log "OVH network firewall: allow TCP ${VNC_PORT} in the manager if still blocked externally"
