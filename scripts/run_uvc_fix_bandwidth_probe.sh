#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-480}"
FPS="${FPS:-30}"
DURATION="${DURATION:-8}"
QUIRKS="${QUIRKS:-128}"
REPORT="${REPORT:-}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo $0"
    exit 1
fi

cd "$PROJECT_ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python not found or not executable: $PYTHON_BIN"
    exit 1
fi

echo "Reloading uvcvideo with quirks=$QUIRKS"
if ! modprobe -r uvcvideo; then
    echo "Failed to unload uvcvideo. Close all camera users and retry."
    exit 1
fi
modprobe uvcvideo "quirks=$QUIRKS"

echo -n "uvcvideo quirks="
cat /sys/module/uvcvideo/parameters/quirks

echo "Waiting for V4L2 devices to enumerate"
sleep 3

echo "Current V4L2 devices:"
v4l2-ctl --list-devices || true

REPORT_ARGS=()
if [[ -n "$REPORT" ]]; then
    REPORT_ARGS=(--output "$REPORT")
fi

echo "USB camera diagnostic report"
"$PYTHON_BIN" scripts/diagnose_usb_cameras.py \
    --max-devices 4 \
    --width "$WIDTH" \
    --height "$HEIGHT" \
    --fps "$FPS" \
    --duration "$DURATION" \
    "${REPORT_ARGS[@]}"
