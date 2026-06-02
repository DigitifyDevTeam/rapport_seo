#!/usr/bin/env bash
set -euo pipefail

# noVNC server for manual browser login on a headless VPS.
# Exposes: http://0.0.0.0:7900  (VNC password: vnc)

export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}"
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}" || true

# Xvfb display + lightweight WM.
if ! pgrep -x Xvfb >/dev/null 2>&1; then
  Xvfb "${DISPLAY}" -screen 0 1440x900x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
fi
sleep 0.4

if ! pgrep -x fluxbox >/dev/null 2>&1; then
  fluxbox >/tmp/fluxbox.log 2>&1 &
fi

# VNC (password file).
mkdir -p /tmp/vnc
PASSFILE=/tmp/vnc/passwd
if [[ ! -f "${PASSFILE}" ]]; then
  x11vnc -storepasswd "vnc" "${PASSFILE}" >/dev/null 2>&1 || true
fi

if ! pgrep -x x11vnc >/dev/null 2>&1; then
  x11vnc \
    -display "${DISPLAY}" \
    -rfbauth "${PASSFILE}" \
    -forever \
    -shared \
    -rfbport 5900 \
    -nopw -localhost 0 \
    >/tmp/x11vnc.log 2>&1 &
fi

# noVNC web proxy (websockify).
NOVNC_WEB=/usr/share/novnc
if [[ ! -d "${NOVNC_WEB}" ]]; then
  # Fallback path on some distros/images.
  NOVNC_WEB=/usr/share/novnc/www
fi

echo "noVNC: http://0.0.0.0:7900  (password: vnc)"
exec websockify --web "${NOVNC_WEB}" 0.0.0.0:7900 localhost:5900

