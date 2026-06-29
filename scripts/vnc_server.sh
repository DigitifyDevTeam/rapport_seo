#!/usr/bin/env bash
set -uo pipefail

# noVNC for manual GMB login on a headless VPS.
# Open: http://<vps-ip>:7900/vnc.html  password: vnc

export DISPLAY="${DISPLAY:-:99}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}"
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}" || true

VNC_PORT=5900
WEB_PORT=7900
DISPLAY_NUM="${DISPLAY#:}"

_log() { echo "[vnc] $*" >&2; }

_http_ready() {
  if command -v curl >/dev/null 2>&1; then
    curl -sf -o /dev/null -m 2 "http://127.0.0.1:${WEB_PORT}/vnc.html"
    return $?
  fi
  python3 - <<PY
import urllib.request
urllib.request.urlopen("http://127.0.0.1:${WEB_PORT}/vnc.html", timeout=2)
PY
}

_wait_http_ready() {
  local tries="${1:-40}"
  local i
  for i in $(seq 1 "${tries}"); do
    if _http_ready; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

_cleanup_display() {
  pkill -9 -f '[w]ebsockify' 2>/dev/null || true
  pkill -9 -f '[x]11vnc' 2>/dev/null || true
  pkill -9 -x fluxbox 2>/dev/null || true
  pkill -9 -x xterm 2>/dev/null || true
  pkill -9 -x Xvfb 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${VNC_PORT}"/tcp "${WEB_PORT}"/tcp 2>/dev/null || true
  fi
  rm -f "/tmp/.X${DISPLAY_NUM}-lock" 2>/dev/null || true
  rm -f "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true
  sleep 0.5
}

_start_xvfb() {
  _log "starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 1440x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  local i
  for i in $(seq 1 50); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
      _log "Xvfb ready on ${DISPLAY}"
      return 0
    fi
    sleep 0.2
  done
  _log "Xvfb did not become ready; see /tmp/xvfb.log"
  tail -20 /tmp/xvfb.log 2>/dev/null || true
  return 1
}

_start_fluxbox() {
  fluxbox -display "${DISPLAY}" >/tmp/fluxbox.log 2>&1 &
  sleep 0.3
}

_start_terminal() {
  if command -v xterm >/dev/null 2>&1; then
    _log "starting xterm"
    xterm -display "${DISPLAY}" -geometry 100x30+40+40 >/tmp/xterm.log 2>&1 &
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
  pgrep -f '[x]11vnc' >/dev/null 2>&1
}

_websockify_healthy() {
  pgrep -f '[w]ebsockify' >/dev/null 2>&1 && _http_ready
}

_start_x11vnc() {
  if _x11vnc_healthy; then
    _log "x11vnc already running"
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
  sleep 1
  if ! _x11vnc_healthy; then
    _log "x11vnc failed to start"
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
  if ! _wait_http_ready 40; then
    _log "websockify did not serve /vnc.html on port ${WEB_PORT}"
    tail -30 /tmp/websockify.log 2>/dev/null || true
    return 1
  fi
  _log "websockify ready on port ${WEB_PORT}"
}

_restart_x11vnc() {
  pkill -9 -f '[x]11vnc' 2>/dev/null || true
  sleep 0.5
  _start_x11vnc
}

_restart_websockify() {
  pkill -9 -f '[w]ebsockify' 2>/dev/null || true
  sleep 0.5
  _start_websockify
}

_cleanup_display

if ! _start_xvfb; then
  _log "FATAL: could not start Xvfb"
  exit 1
fi
_start_fluxbox
_start_terminal

if ! _start_x11vnc; then
  _log "FATAL: could not start x11vnc"
  exit 1
fi
if ! _start_websockify; then
  _log "FATAL: could not start websockify"
  exit 1
fi

_log "noVNC: http://0.0.0.0:${WEB_PORT}/vnc.html  (password: vnc)"

while true; do
  if ! _x11vnc_healthy; then
    _log "x11vnc unhealthy; restarting"
    tail -10 /tmp/x11vnc.log 2>/dev/null || true
    _restart_x11vnc || true
  fi
  if ! _websockify_healthy; then
    _log "websockify unhealthy; restarting"
    tail -10 /tmp/websockify.log 2>/dev/null || true
    _restart_websockify || true
  fi
  sleep 5
done
