#!/usr/bin/env bash
set -euo pipefail

# noVNC for manual GMB login on a headless VPS.
# Open: http://<vps-ip>:7900/vnc.html  password: vnc
#
# Important: websockify proxies to localhost:5900, so x11vnc MUST stay alive.

export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}"
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}" || true

VNC_PORT=5900
WEB_PORT=7900

# Logs must go to stderr — stdout is used for function return values (paths, PIDs).
_log() { echo "[vnc] $*" >&2; }

_port_listening() {
  local port="${1:?port}"
  if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | grep -qE ":${port}\\b"
    return $?
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | grep -qE ":${port}\\b"
    return $?
  fi
  # Fallback: avoid probing the VNC port (raw TCP causes x11vnc log noise).
  return 1
}

_wait_port_listening() {
  local port="${1:?port}"
  local tries="${2:-40}"
  local i
  for i in $(seq 1 "${tries}"); do
    if _port_listening "${port}"; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

_kill_vnc_listeners() {
  pkill -9 -f '[w]ebsockify' 2>/dev/null || true
  pkill -9 -f '[x]11vnc' 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${VNC_PORT}"/tcp "${WEB_PORT}"/tcp 2>/dev/null || true
  fi
  sleep 0.4
}

_start_xvfb() {
  if pgrep -x Xvfb >/dev/null 2>&1; then
    return 0
  fi
  _log "starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 1440x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  local i
  for i in $(seq 1 40); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  _log "Xvfb did not become ready; see /tmp/xvfb.log"
  tail -20 /tmp/xvfb.log 2>/dev/null || true
  return 1
}

_start_fluxbox() {
  if pgrep -x fluxbox >/dev/null 2>&1; then
    return 0
  fi
  fluxbox >/tmp/fluxbox.log 2>&1 &
  sleep 0.3
}

_start_terminal() {
  if pgrep -x xterm >/dev/null 2>&1; then
    return 0
  fi
  if command -v xterm >/dev/null 2>&1; then
    _log "starting xterm (right-click desktop also opens Fluxbox menu)"
    xterm -geometry 100x30+40+40 >/tmp/xterm.log 2>&1 &
  fi
}

_ensure_passfile() {
  mkdir -p /tmp/vnc
  local passfile=/tmp/vnc/passwd
  if [[ ! -f "${passfile}" ]]; then
    x11vnc -storepasswd "vnc" "${passfile}" >/dev/null 2>&1
  fi
  echo "${passfile}"
}

_find_novnc_web() {
  local candidate
  for candidate in /usr/share/novnc /usr/share/novnc/www /usr/share/nodejs/novnc; do
    if [[ -f "${candidate}/vnc.html" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

_x11vnc_healthy() {
  pgrep -f '[x]11vnc' >/dev/null 2>&1 && _port_listening "${VNC_PORT}"
}

_websockify_healthy() {
  pgrep -f '[w]ebsockify' >/dev/null 2>&1 && _port_listening "${WEB_PORT}"
}

_start_x11vnc() {
  if _x11vnc_healthy; then
    _log "x11vnc already running on port ${VNC_PORT}"
    return 0
  fi
  local passfile
  passfile="$(_ensure_passfile)"
  _log "starting x11vnc on port ${VNC_PORT}"
  x11vnc \
    -display "${DISPLAY}" \
    -rfbauth "${passfile}" \
    -forever \
    -shared \
    -rfbport "${VNC_PORT}" \
    -listen 127.0.0.1 \
    -noxdamage \
    >/tmp/x11vnc.log 2>&1 &
  if ! _wait_port_listening "${VNC_PORT}" 30; then
    _log "x11vnc did not open port ${VNC_PORT}"
    tail -30 /tmp/x11vnc.log 2>/dev/null || true
    return 1
  fi
  _log "x11vnc ready on port ${VNC_PORT}"
}

_start_websockify() {
  if _websockify_healthy; then
    _log "websockify already running on port ${WEB_PORT}"
    return 0
  fi
  local novnc_web
  novnc_web="$(_find_novnc_web)" || {
    _log "ERROR: vnc.html not found under /usr/share/novnc"
    return 1
  }
  _log "starting websockify on ${WEB_PORT} -> ${VNC_PORT} (web=${novnc_web})"
  websockify --web "${novnc_web}" "0.0.0.0:${WEB_PORT}" "localhost:${VNC_PORT}" \
    >/tmp/websockify.log 2>&1 &
  if ! _wait_port_listening "${WEB_PORT}" 30; then
    _log "websockify did not open port ${WEB_PORT}"
    tail -30 /tmp/websockify.log 2>/dev/null || true
    return 1
  fi
  _log "websockify ready on port ${WEB_PORT}"
}

_restart_x11vnc() {
  pkill -9 -f '[x]11vnc' 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${VNC_PORT}"/tcp 2>/dev/null || true
  fi
  sleep 0.5
  _start_x11vnc
}

_restart_websockify() {
  pkill -9 -f '[w]ebsockify' 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${WEB_PORT}"/tcp 2>/dev/null || true
  fi
  sleep 0.5
  _start_websockify
}

_kill_vnc_listeners

_start_xvfb
_start_fluxbox
_start_terminal

_start_x11vnc
_start_websockify

_log "noVNC: http://0.0.0.0:${WEB_PORT}/vnc.html  (password: vnc)"

while true; do
  if ! _x11vnc_healthy; then
    _log "x11vnc unhealthy; restarting (tail /tmp/x11vnc.log):"
    tail -10 /tmp/x11vnc.log 2>/dev/null || true
    _restart_x11vnc || true
  fi
  if ! _websockify_healthy; then
    _log "websockify unhealthy; restarting (tail /tmp/websockify.log):"
    tail -10 /tmp/websockify.log 2>/dev/null || true
    _restart_websockify || true
  fi
  sleep 5
done
