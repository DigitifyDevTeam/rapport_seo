#!/usr/bin/env bash
set -euo pipefail

# noVNC for manual GMB login on a headless VPS.
# Open: http://<vps-ip>:7900/vnc.html  password: vnc

export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}"
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}" || true

_log() { echo "[vnc] $*"; }

_start_xvfb() {
  if pgrep -x Xvfb >/dev/null 2>&1; then
    return 0
  fi
  _log "starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 1440x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  for _ in $(seq 1 30); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  _log "Xvfb did not become ready; see /tmp/xvfb.log"
  return 1
}

_start_fluxbox() {
  if pgrep -x fluxbox >/dev/null 2>&1; then
    return 0
  fi
  fluxbox >/tmp/fluxbox.log 2>&1 &
  sleep 0.3
}

_start_x11vnc() {
  if pgrep -x x11vnc >/dev/null 2>&1; then
    return 0
  fi
  mkdir -p /tmp/vnc
  PASSFILE=/tmp/vnc/passwd
  if [[ ! -f "${PASSFILE}" ]]; then
    x11vnc -storepasswd "vnc" "${PASSFILE}" >/dev/null 2>&1
  fi
  _log "starting x11vnc on port 5900"
  x11vnc \
    -display "${DISPLAY}" \
    -rfbauth "${PASSFILE}" \
    -forever \
    -shared \
    -rfbport 5900 \
    -listen 0.0.0.0 \
    -noxdamage \
    >/tmp/x11vnc.log 2>&1 &
  for _ in $(seq 1 30); do
    if ss -lntp 2>/dev/null | grep -q ':5900 '; then
      _log "x11vnc listening on 5900"
      return 0
    fi
    sleep 0.2
  done
  _log "x11vnc failed to listen; tail /tmp/x11vnc.log:"
  tail -20 /tmp/x11vnc.log 2>/dev/null || true
  return 1
}

_start_xvfb
_start_fluxbox
_start_x11vnc

NOVNC_WEB=/usr/share/novnc
if [[ ! -d "${NOVNC_WEB}" ]]; then
  NOVNC_WEB=/usr/share/novnc/www
fi

_log "noVNC: http://0.0.0.0:7900/vnc.html  (password: vnc)"
exec websockify --web "${NOVNC_WEB}" 0.0.0.0:7900 localhost:5900
