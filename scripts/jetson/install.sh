#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
SKIP_SYSTEM=0
SKIP_PYTHON=0
INSTALL_DESKTOP=1

usage() {
    cat <<'EOF'
用法: ./scripts/jetson/install.sh [选项]
  --skip-system-packages  不运行 apt（用于已准备好的机器或测试）
  --skip-python-deps      不创建虚拟环境、不安装 Python 依赖
  --no-desktop            不安装桌面图标
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-system-packages) SKIP_SYSTEM=1 ;;
        --skip-python-deps) SKIP_PYTHON=1 ;;
        --no-desktop) INSTALL_DESKTOP=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "警告：当前架构为 $(uname -m)，正式发布目标是 aarch64。" >&2
fi

validate_opencv() {
    "$1" - <<'PY'
import cv2
build = cv2.getBuildInformation()
enabled = any(
    line.strip().startswith("GStreamer:") and "YES" in line.upper()
    for line in build.splitlines()
)
print("OpenCV", cv2.__version__, "from", cv2.__file__)
print("GStreamer:", "YES" if enabled else "NO")
if not enabled:
    raise SystemExit("OpenCV 必须启用 GStreamer；请移除 pip opencv 并安装 Jetson/Ubuntu 原生包。")
PY
}

SYSTEM_PACKAGES=(
    python3 python3-pip python3-venv python3-dev
    python3-pyqt5 python3-numpy python3-pandas python3-pil
    python3-gi gir1.2-gstreamer-1.0
    gstreamer1.0-tools gstreamer1.0-plugins-base
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
    gstreamer1.0-libav v4l-utils
    libgl1 libegl1 libgles2 libxcb-xinerama0 libxcb-xinput0
    desktop-file-utils zenity
)

if [[ $SKIP_SYSTEM -eq 0 ]]; then
    MISSING_PACKAGES=()
    for package in "${SYSTEM_PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null \
            | grep -q '^install ok installed$'; then
            MISSING_PACKAGES+=("$package")
        fi
    done

    # JetPack may provide a GStreamer-enabled cv2 outside the Ubuntu
    # python3-opencv package. Preserve that verified build instead of replacing
    # it with the older Ubuntu archive.
    if ! validate_opencv /usr/bin/python3; then
        MISSING_PACKAGES+=(python3-opencv)
    fi

    if [[ ${#MISSING_PACKAGES[@]} -gt 0 ]]; then
        command -v sudo >/dev/null 2>&1 || {
            echo "安装缺失的系统依赖需要 sudo：${MISSING_PACKAGES[*]}" >&2
            exit 1
        }
        echo "需要安装系统依赖：${MISSING_PACKAGES[*]}"
        if ! sudo apt-get update; then
            echo "apt 软件源更新失败。请修复网络或软件源后重试。" >&2
            exit 1
        fi
        if ! sudo apt-get install -y "${MISSING_PACKAGES[@]}"; then
            echo "系统依赖下载失败。当前配置的软件源可能不可达。" >&2
            echo "修复软件源后重试；不要用 pip opencv 替代 Jetson 原生 OpenCV。" >&2
            exit 1
        fi
    else
        echo "系统依赖和 GStreamer OpenCV 已就绪，跳过 apt。"
    fi
else
    validate_opencv /usr/bin/python3
fi

if [[ $SKIP_PYTHON -eq 0 ]]; then
    VENV="$APP_ROOT/.venv-jetson"
    if [[ ! -x "$VENV/bin/python" ]]; then
        /usr/bin/python3 -m venv --system-site-packages "$VENV"
    fi
    # Do not inherit a stale user-level mirror for this installation. The
    # source remains overridable for offline/LAN mirrors without modifying
    # ~/.config/pip or ~/.bashrc.
    PIP_INDEX_URL="${CAMERA_SYSTEM_PIP_INDEX_URL:-https://pypi.org/simple}"
    PIP_GLOBAL_ARGS=(
        --isolated
        --disable-pip-version-check
    )
    echo "Python 依赖源：$PIP_INDEX_URL"
    "$VENV/bin/python" -m pip "${PIP_GLOBAL_ARGS[@]}" install \
        --index-url "$PIP_INDEX_URL" --upgrade \
        "pip<25" "setuptools<76" wheel
    "$VENV/bin/python" -m pip "${PIP_GLOBAL_ARGS[@]}" install \
        --index-url "$PIP_INDEX_URL" \
        -r "$APP_ROOT/requirements/jetson.txt"
    "$VENV/bin/python" -m pip "${PIP_GLOBAL_ARGS[@]}" install \
        --index-url "$PIP_INDEX_URL" --no-deps -e "$APP_ROOT"
    validate_opencv "$VENV/bin/python"
fi

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/camera-system"
mkdir -p "$CONFIG_DIR"
if [[ ! -e "$CONFIG_DIR/settings.yaml" ]]; then
    cp "$APP_ROOT/config/examples/settings.yaml" "$CONFIG_DIR/settings.yaml"
    echo "已创建配置：$CONFIG_DIR/settings.yaml"
fi

chmod +x \
    "$APP_ROOT/scripts/jetson/install.sh" \
    "$APP_ROOT/scripts/jetson/run.sh" \
    "$APP_ROOT/scripts/jetson/release.sh" \
    "$APP_ROOT/scripts/jetson/diagnose.sh"

if [[ $INSTALL_DESKTOP -eq 1 ]]; then
    ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
    APPLICATION_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
    mkdir -p "$ICON_DIR" "$APPLICATION_DIR" "$DESKTOP_DIR"
    ICON_PATH="$ICON_DIR/camera-system.svg"
    cp "$APP_ROOT/resources/icons/camera-system.svg" "$ICON_PATH"

    install_desktop_file() {
        local destination="$1"
        sed \
            -e "s|@APP_ROOT@|$APP_ROOT|g" \
            -e "s|@ICON_PATH@|$ICON_PATH|g" \
            "$APP_ROOT/packaging/linux/camera-system.desktop" > "$destination"
        chmod +x "$destination"
    }

    install_desktop_file "$APPLICATION_DIR/camera-system.desktop"
    install_desktop_file "$DESKTOP_DIR/camera-system.desktop"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$APPLICATION_DIR" >/dev/null 2>&1 || true
    command -v gio >/dev/null 2>&1 \
        && gio set "$DESKTOP_DIR/camera-system.desktop" metadata::trusted true >/dev/null 2>&1 || true
    echo "桌面入口已安装：$DESKTOP_DIR/camera-system.desktop"
fi

echo "安装完成。请先编辑 $CONFIG_DIR/settings.yaml 中的 wsl_service_url。"
echo "诊断命令：$APP_ROOT/scripts/jetson/diagnose.sh"
