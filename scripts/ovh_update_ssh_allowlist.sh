#!/usr/bin/env bash
# Allow SSH from a new public IP on the OVH host (ufw or iptables).
#
# Configure in `.env` (see .env.server.example):
#   OVH_SERVER_IP, SSH_ALLOWED_IP_OLD, SSH_ALLOWED_IP_NEW
#
# Run ON THE SERVER (root or sudo), e.g. after OVH rescue or from a shell on the host:
#   cd ~/public_html/rapport_seo   # or /opt/rapport_seo
#   sudo ./scripts/ovh_update_ssh_allowlist.sh
#
# Or pass the new IP directly:
#   sudo ./scripts/ovh_update_ssh_allowlist.sh 197.5.150.236
#
# Replace old rule (remove OLD then add NEW):
#   sudo ./scripts/ovh_update_ssh_allowlist.sh --replace-old
#
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

_log() { echo "[ovh-ssh] $*"; }
_die() { echo "[ovh-ssh] ERROR: $*" >&2; exit 1; }

_is_ip() {
  local ip="${1:?}"
  [[ "${ip}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

REPLACE_OLD=0
NEW_IP_CLI=""
for arg in "$@"; do
  case "${arg}" in
    --replace-old) REPLACE_OLD=1 ;;
    -h | --help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *)
      if [[ -z "${NEW_IP_CLI}" ]] && _is_ip "${arg}" 2>/dev/null; then
        NEW_IP_CLI="${arg}"
      fi
      ;;
  esac
done

_load_env

SSH_PORT="${SSH_PORT:-22}"
OLD_IP="${SSH_ALLOWED_IP_OLD:-}"
NEW_IP="${NEW_IP_CLI:-${SSH_ALLOWED_IP_NEW:-}}"
SERVER_IP="${OVH_SERVER_IP:-}"

if [[ -z "${NEW_IP}" ]]; then
  _die "Set SSH_ALLOWED_IP_NEW in .env or pass the IP as an argument (your PC IP from https://api.ipify.org, not ${SERVER_IP:-the server IP})."
fi

if ! _is_ip "${NEW_IP}"; then
  _die "Invalid IP: ${NEW_IP}"
fi

if [[ -n "${OLD_IP}" ]] && ! _is_ip "${OLD_IP}"; then
  _die "Invalid SSH_ALLOWED_IP_OLD: ${OLD_IP}"
fi

if [[ "${NEW_IP}" == "${SERVER_IP}" ]]; then
  _log "WARNING: NEW_IP equals OVH_SERVER_IP — that is the server itself, not your office. Use api.ipify.org from your PC."
fi

if [[ "$(id -u)" -ne 0 ]]; then
  _die "Run with sudo on the OVH host."
fi

_ufw_allow() {
  local ip="${1:?}"
  if ufw status 2>/dev/null | grep -qF "${ip}"; then
    _log "ufw: rule for ${ip} already present"
    return 0
  fi
  ufw allow from "${ip}" to any port "${SSH_PORT}" proto tcp comment "rapport_seo allowlist"
  _log "ufw: allowed ${ip} -> tcp/${SSH_PORT}"
}

_ufw_delete_old() {
  local ip="${1:?}"
  if ufw status 2>/dev/null | grep -qF "${ip}"; then
    ufw delete allow from "${ip}" to any port "${SSH_PORT}" proto tcp 2>/dev/null \
      || ufw delete allow from "${ip}" 2>/dev/null \
      || true
    _log "ufw: removed allow rule for ${ip}"
  else
    _log "ufw: no rule found for ${ip} (skip delete)"
  fi
}

_iptables_allow() {
  local ip="${1:?}"
  if iptables -C INPUT -s "${ip}" -p tcp --dport "${SSH_PORT}" -j ACCEPT 2>/dev/null; then
    _log "iptables: rule for ${ip} already present"
    return 0
  fi
  iptables -I INPUT -s "${ip}" -p tcp --dport "${SSH_PORT}" -j ACCEPT
  _log "iptables: allowed ${ip} -> tcp/${SSH_PORT}"
}

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi "Status: active"; then
  _log "Using ufw (active)"
  if [[ "${REPLACE_OLD}" -eq 1 && -n "${OLD_IP}" ]]; then
    _ufw_delete_old "${OLD_IP}"
  fi
  _ufw_allow "${NEW_IP}"
  ufw reload 2>/dev/null || true
  echo ""
  ufw status | grep -E "Status:|${NEW_IP}|${SSH_PORT}" || ufw status
elif command -v ufw >/dev/null 2>&1; then
  _log "ufw installed but not active — enabling default deny with SSH allow..."
  ufw --force enable 2>/dev/null || true
  _ufw_allow "${NEW_IP}"
  ufw reload 2>/dev/null || true
else
  _log "ufw not active — using iptables"
  _iptables_allow "${NEW_IP}"
  _log "Persist iptables on Debian: apt install iptables-persistent && netfilter-persistent save"
fi

echo ""
_log "Done. From your PC test:"
if [[ -n "${OVH_SSH_USER:-}" ]]; then
  echo "  ssh ${OVH_SSH_USER}@${SERVER_IP:-94.23.210.145}"
else
  echo "  ssh YOUR_USER@${SERVER_IP:-94.23.210.145}"
fi
_log "Also add ${NEW_IP} in OVH Manager → IP → Firewall Network if the block is at OVH edge."
