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

_log() { echo "[vnc] $*"; }

_start_xvfb() {
  if pgrep -x Xvfb >/dev/null 2>&1; then
    return 0
  fi
  _log "starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 1440x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  for _ in $(seq 1 40); do
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

_ensure_passfile() {
  mkdir -p /tmp/vnc
  PASSFILE=/tmp/vnc/passwd
  if [[ ! -f "${PASSFILE}" ]]; then
    x11vnc -storepasswd "vnc" "${PASSFILE}" >/dev/null 2>&1
  fi
  echo "${PASSFILE}"
}

_start_x11vnc() {
  local passfile
  passfile="$(_ensure_passfile)"
  _log "starting x11vnc on port 5900"
  x11vnc \
    -display "${DISPLAY}" \
    -rfbauth "${passfile}" \
    -forever \
    -shared \
    -rfbport 5900 \
    -listen 127.0.0.1 \
    -noxdamage \
    >/tmp/x11vnc.log 2>&1 &
  echo $!
}

_start_websockify() {
  NOVNC_WEB=/usr/share/novnc
  if [[ ! -d "${NOVNC_WEB}" ]]; then
    NOVNC_WEB=/usr/share/novnc/www
  fi
  _log "starting websockify on 7900 -> 5900"
  websockify --web "${NOVNC_WEB}" 0.0.0.0:7900 localhost:5900 >/tmp/websockify.log 2>&1 &
  echo $!
}

_port_open() {
  local host="${1:?host}"
  local port="${2:?port}"
  python - <<PY
import socket
host = ${host!r}
port = int(${port!r})
s = socket.socket()
s.settimeout(0.5)
try:
  s.connect((host, port))
  print("open")
except Exception:
  print("closed")
finally:
  s.close()
PY
}

_start_xvfb
_start_fluxbox

# Clean up any stray processes from previous starts.
pkill -f "websockify.*0\\.0\\.0\\.0:7900" 2>/dev/null || true
pkill -f "websockify.*:7900" 2>/dev/null || true
pkill -f x11vnc 2>/dev/null || true
sleep 0.4

X11VNC_PID="$(_start_x11vnc)"
WEBSOCKIFY_PID="$(_start_websockify)"

_log "noVNC: http://0.0.0.0:7900/vnc.html  (password: vnc)"

while true; do
  # If x11vnc died, websockify will fail with connection refused.
  if ! kill -0 "${X11VNC_PID}" >/dev/null 2>&1; then
    _log "x11vnc stopped; restarting (tail /tmp/x11vnc.log):"
    tail -50 /tmp/x11vnc.log 2>/dev/null || true
    X11VNC_PID="$(_start_x11vnc)"
  fi
  # Ensure the VNC port is reachable locally.
  if [[ "$(_port_open 127.0.0.1 5900)" != "open" ]]; then
    _log "port 5900 not reachable yet; waiting..."
  fi
  # If websockify died, restart it too.
  if ! kill -0 "${WEBSOCKIFY_PID}" >/dev/null 2>&1; then
    _log "websockify stopped; restarting (tail /tmp/websockify.log):"
    tail -50 /tmp/websockify.log 2>/dev/null || true
    WEBSOCKIFY_PID="$(_start_websockify)"
  fi
  sleep 1
done
