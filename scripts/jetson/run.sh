#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
export CAMERA_SYSTEM_PROJECT_ROOT="${CAMERA_SYSTEM_PROJECT_ROOT:-$APP_ROOT}"

choose_python() {
    local candidate
    for candidate in \
        "${CAMERA_SYSTEM_PYTHON:-}" \
        "$APP_ROOT/.venv-jetson/bin/python" \
        "$APP_ROOT/multiwebcam/.venv-jetson/bin/python" \
        /usr/bin/python3; do
        if [[ -n "$candidate" && -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(choose_python)" || {
    echo "未找到可用的 Python 3 运行时。" >&2
    exit 127
}

prepend_path() {
    local variable="$1"
    local value="$2"
    local current="${!variable:-}"
    [[ -d "$value" ]] || return 0
    if [[ -n "$current" ]]; then
        export "$variable=$value:$current"
    else
        export "$variable=$value"
    fi
}

prepend_path PYTHONPATH "$APP_ROOT/3DGSviewer/q3dviewer"
prepend_path PYTHONPATH "$APP_ROOT/Tx_Rx"
prepend_path PYTHONPATH "$APP_ROOT/multiwebcam/src"
prepend_path PYTHONPATH "$APP_ROOT/src"

QT_PLUGIN_ROOT="/usr/lib/$(uname -m)-linux-gnu/qt5/plugins"
if [[ -d "$QT_PLUGIN_ROOT" ]]; then
    prepend_path QT_PLUGIN_PATH "$QT_PLUGIN_ROOT"
    if [[ -d "$QT_PLUGIN_ROOT/platforms" ]]; then
        export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGIN_ROOT/platforms"
    fi
fi

export Q3D_QT_IMPL=PySide6
export QT_OPENGL="${QT_OPENGL:-desktop}"
export PYTHONUNBUFFERED=1

# JetPack 提供 EGL/GLES/OpenGL；只补充调度库，不替换 NVIDIA 原生库路径。
if [[ "$(uname -m)" == "aarch64" ]]; then
    GLDISPATCH="/usr/lib/aarch64-linux-gnu/libGLdispatch.so.0"
    [[ -f "$GLDISPATCH" ]] || GLDISPATCH="/lib/aarch64-linux-gnu/libGLdispatch.so.0"
    if [[ -f "$GLDISPATCH" && ":${LD_PRELOAD:-}:" != *":$GLDISPATCH:"* ]]; then
        export LD_PRELOAD="$GLDISPATCH${LD_PRELOAD:+:$LD_PRELOAD}"
    fi
fi

USER_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/camera-system/settings.yaml"
if [[ -z "${CAMERA_SYSTEM_CONFIG:-}" && -f "$USER_CONFIG" ]]; then
    export CAMERA_SYSTEM_CONFIG="$USER_CONFIG"
fi

if [[ "${1:-}" == "--diagnose-dialog" ]]; then
    shift
    set +e
    OUTPUT="$("$PYTHON_BIN" -m camera_system_app --project-root "$APP_ROOT" --diagnose "$@" 2>&1)"
    STATUS=$?
    set -e
    if command -v zenity >/dev/null 2>&1; then
        if [[ $STATUS -eq 0 ]]; then
            zenity --info --title="Camera System 环境诊断" --width=760 --text="$OUTPUT"
        else
            zenity --error --title="Camera System 环境诊断" --width=760 --text="$OUTPUT"
        fi
    elif command -v xmessage >/dev/null 2>&1; then
        xmessage -center "$OUTPUT"
    else
        printf '%s\n' "$OUTPUT"
    fi
    exit "$STATUS"
fi

exec "$PYTHON_BIN" -m camera_system_app --project-root "$APP_ROOT" "$@"
