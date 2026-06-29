#!/usr/bin/env bash
# Diagnose noVNC (port 7900) on the VPS.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

VNC_PORT="${VNC_PORT:-7900}"
FAIL=0

echo "=== seo-vnc container ==="
if docker compose --profile tools ps seo-vnc 2>/dev/null | grep -q "Up"; then
  echo "OK  container is Up"
else
  echo "FAIL container not running"
  FAIL=1
fi

echo ""
echo "=== Docker port publish (host) ==="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep -E ":${VNC_PORT}\\b" || {
    echo "FAIL nothing listening on 0.0.0.0:${VNC_PORT} on the host"
    FAIL=1
  }
elif command -v netstat >/dev/null 2>&1; then
  netstat -tlnp 2>/dev/null | grep -E ":${VNC_PORT}\\b" || {
    echo "FAIL nothing listening on :${VNC_PORT} on the host"
    FAIL=1
  }
else
  echo "SKIP ss/netstat not found"
fi

echo ""
echo "=== HTTP from host (docker port mapping) ==="
if curl -sf -o /dev/null -m 5 "http://127.0.0.1:${VNC_PORT}/vnc.html"; then
  echo "OK  http://127.0.0.1:${VNC_PORT}/vnc.html"
else
  echo "FAIL curl to 127.0.0.1:${VNC_PORT}/vnc.html"
  FAIL=1
fi

echo ""
echo "=== Inside container ==="
if docker compose --profile tools ps seo-vnc 2>/dev/null | grep -q "Up"; then
  docker compose --profile tools exec -T seo-vnc bash -lc "
    echo '--- processes ---'
    pgrep -a websockify || echo 'websockify: not running'
    pgrep -a x11vnc || echo 'x11vnc: not running'
    pgrep -a Xvfb || echo 'Xvfb: not running'
    echo '--- novnc web root ---'
    for d in /usr/share/novnc /usr/share/novnc/www; do
      if [[ -f \"\${d}/vnc.html\" ]]; then echo \"OK  \${d}/vnc.html\"; fi
    done
    echo '--- logs (tail) ---'
    tail -20 /tmp/websockify.log 2>/dev/null || true
    tail -20 /tmp/x11vnc.log 2>/dev/null || true
    tail -20 /tmp/xvfb.log 2>/dev/null || true
  " || true
fi

echo ""
echo "=== Host firewall (ufw) ==="
if command -v ufw >/dev/null 2>&1; then
  ufw status 2>/dev/null | head -20 || true
  if ufw status 2>/dev/null | grep -qi "Status: active"; then
    if ufw status 2>/dev/null | grep -qE "${VNC_PORT}/tcp|${VNC_PORT} "; then
      echo "OK  ufw has a rule for port ${VNC_PORT}"
    else
      echo "WARN ufw is active but port ${VNC_PORT} may be blocked"
      echo "      See: ./scripts/vnc_open_firewall.sh  (SSH tunnel or OVH Manager)"
      FAIL=1
    fi
  else
    echo "INFO ufw installed but not active"
  fi
else
  echo "INFO ufw not installed — check OVH network firewall in the manager"
fi

echo ""
if [[ "${FAIL}" -eq 0 ]]; then
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "noVNC should work at: http://${IP:-<vps-ip>}:${VNC_PORT}/vnc.html  (password: vnc)"
  echo "If the browser still fails from your PC, see: ./scripts/vnc_open_firewall.sh"
  echo "  (SSH tunnel or OVH Manager firewall for port ${VNC_PORT})"
else
  echo "noVNC is NOT ready. Fix the FAIL items above, then:"
  echo "  ./scripts/vnc_start.sh"
  echo "  ./scripts/vnc_health.sh"
  exit 1
fi
