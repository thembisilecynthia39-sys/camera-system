#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
VERSION="$(PYTHONPATH="$APP_ROOT/src" /usr/bin/python3 -c 'from camera_system_app import __version__; print(__version__)')"
OUTPUT_ROOT="${CAMERA_SYSTEM_DIST_DIR:-$APP_ROOT/dist}"
PACKAGE_NAME="camera-system-${VERSION}-jetson-arm64"
TARGET="$OUTPUT_ROOT/$PACKAGE_NAME"

if [[ $# -gt 0 ]]; then
    if [[ "$1" == "--output" && $# -eq 2 ]]; then
        OUTPUT_ROOT="$(realpath -m "$2")"
        TARGET="$OUTPUT_ROOT/$PACKAGE_NAME"
    else
        echo "用法: ./scripts/jetson/release.sh [--output 目录]" >&2
        exit 2
    fi
fi

mkdir -p "$OUTPUT_ROOT"
if [[ -e "$TARGET" || -e "$TARGET.tar.gz" ]]; then
    echo "发布目标已存在，请移走后重试：$TARGET" >&2
    exit 1
fi

TEMP_ROOT="$(mktemp -d "$OUTPUT_ROOT/.camera-system-release.XXXXXX")"
trap 'rm -rf "$TEMP_ROOT"' EXIT
mkdir -p "$TEMP_ROOT/$PACKAGE_NAME"

tar -C "$APP_ROOT" \
    --exclude='./.git' \
    --exclude='./.git-history-backups' \
    --exclude='./.agents' \
    --exclude='./.codex' \
    --exclude='./.pytest_cache' \
    --exclude='./.venv*' \
    --exclude='./dist' \
    --exclude='./build' \
    --exclude='./captures' \
    --exclude='./multiwebcam.toml' \
    --exclude='./result' \
    --exclude='./runtime' \
    --exclude='./tests' \
    --exclude='*/__pycache__' \
    --exclude='*/.git' \
    --exclude='*/.vscode' \
    --exclude='*/.pytest_cache' \
    --exclude='*/.ruff_cache' \
    --exclude='*/.venv*' \
    --exclude='*/build' \
    --exclude='*/tests' \
    --exclude='*/captures' \
    --exclude='*/recordings' \
    --exclude='*/staging' \
    --exclude='./Tx_Rx/config.yaml' \
    --exclude='*/artifacts' \
    --exclude='*/archive' \
    --exclude='*.pyc' \
    --exclude='*.egg-info' \
    -cf - . | tar -C "$TEMP_ROOT/$PACKAGE_NAME" -xf -

chmod +x \
    "$TEMP_ROOT/$PACKAGE_NAME/scripts/jetson/install.sh" \
    "$TEMP_ROOT/$PACKAGE_NAME/scripts/jetson/run.sh" \
    "$TEMP_ROOT/$PACKAGE_NAME/scripts/jetson/release.sh" \
    "$TEMP_ROOT/$PACKAGE_NAME/scripts/jetson/diagnose.sh"

mv "$TEMP_ROOT/$PACKAGE_NAME" "$TARGET"
tar -C "$OUTPUT_ROOT" -czf "$TARGET.tar.gz" "$PACKAGE_NAME"
sha256sum "$TARGET.tar.gz" > "$TARGET.tar.gz.sha256"
trap - EXIT
rmdir "$TEMP_ROOT"

echo "应用目录：$TARGET"
echo "压缩包：$TARGET.tar.gz"
echo "校验文件：$TARGET.tar.gz.sha256"
