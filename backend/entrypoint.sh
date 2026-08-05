#!/bin/sh
set -eu

# Headed Chromium (needed to clear Cloudflare on many VPS IPs) requires a display.
if [ -z "${DISPLAY:-}" ]; then
  export DISPLAY=:99
fi

if ! pgrep -x Xvfb >/dev/null 2>&1; then
  Xvfb "$DISPLAY" -screen 0 1920x1080x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
  sleep 0.5
fi

exec "$@"
