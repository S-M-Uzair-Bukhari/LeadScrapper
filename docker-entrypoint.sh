#!/bin/sh
set -eu

Xvfb "${DISPLAY:-:99}" -screen 0 1920x1080x24 -nolisten tcp &
sleep 1
x11vnc \
    -display "${DISPLAY:-:99}" \
    -forever \
    -shared \
    -nopw \
    -rfbport 5900 \
    -quiet &
websockify --web=/usr/share/novnc 7900 localhost:5900 &

exec python main.py "$@"
