"""Lightweight diagnostics that do not open devices or contact services."""

from __future__ import annotations

import importlib.util
import ctypes.util
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List

from camera_system_app.config.settings import AppSettings
from camera_system_app.domain.diagnostics import (
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
)
from camera_system_app.infrastructure.paths import AppPaths
from camera_system_app import __version__

_REQUIRED_JETSON_MODULES = (
    "numpy",
    "cv2",
    "av",
    "yaml",
    "pydantic",
    "requests",
    "OpenGL",
    "PIL",
    "platformdirs",
    "rtoml",
    "meshio",
)
_OPTIONAL_JETSON_MODULES = ("qfluentwidgets", "onnx")


class DiagnosticService:
    """Inspect local availability without starting optional subsystems."""

    def __init__(self, paths: AppPaths, settings: AppSettings) -> None:
        self.paths = paths
        self.settings = settings

    def run(self) -> DiagnosticReport:
        checks = [
            self._runtime_check(),
            self._python_check(),
            self._dependency_check(),
            self._qt_check(),
            self._opencv_check(),
            self._graphics_check(),
            self._workspace_check(),
            self._camera_check(),
            self._wsl_check(),
            self._viewer_check(),
            self._configuration_check(),
            self._log_check(),
        ]
        return DiagnosticReport.from_checks(checks)

    def _runtime_check(self) -> DiagnosticCheck:
        return DiagnosticCheck(
            "应用运行时",
            DiagnosticStatus.PASS,
            "Camera System {}".format(__version__),
            "{} · {} · {}".format(
                platform.platform(),
                platform.machine(),
                sys.executable,
            ),
        )

    def _python_check(self) -> DiagnosticCheck:
        supported = sys.version_info >= (3, 8)
        return DiagnosticCheck(
            "Python",
            DiagnosticStatus.PASS if supported else DiagnosticStatus.FAILURE,
            platform.python_version(),
            sys.executable,
        )

    def _dependency_check(self) -> DiagnosticCheck:
        """Validate project imports without judging unrelated system packages."""

        missing_required = [
            name
            for name in _REQUIRED_JETSON_MODULES
            if importlib.util.find_spec(name) is None
        ]
        missing_optional = [
            name
            for name in _OPTIONAL_JETSON_MODULES
            if importlib.util.find_spec(name) is None
        ]
        optional_notes = [
            "{} 未安装".format(name)
            for name in missing_optional
        ]

        if importlib.util.find_spec("qfluentwidgets") is not None:
            try:
                from PySide6.QtCore import qVersion

                qt_parts = tuple(
                    int(part) for part in qVersion().split(".")[:2]
                )
            except Exception:
                qt_parts = ()
            if qt_parts and qt_parts < (5, 15):
                optional_notes.append(
                    "qfluentwidgets 的包元数据要求 Qt/PyQt >= 5.15；"
                    "当前使用 JetPack Qt 兼容层和内置控件回退"
                )

        if missing_required:
            return DiagnosticCheck(
                "Python 项目依赖",
                DiagnosticStatus.FAILURE,
                "缺少核心运行依赖",
                ", ".join(missing_required),
            )
        if optional_notes:
            return DiagnosticCheck(
                "Python 项目依赖",
                DiagnosticStatus.WARNING,
                "核心运行依赖可用；可选工具不完整",
                "；".join(optional_notes),
            )
        return DiagnosticCheck(
            "Python 项目依赖",
            DiagnosticStatus.PASS,
            "核心及可选项目依赖可用",
            "JetPack 系统组件保持原生版本",
        )

    def _qt_check(self) -> DiagnosticCheck:
        pyside = importlib.util.find_spec("PySide6")
        pyqt = importlib.util.find_spec("PyQt5")
        bundled_shim = self.paths.project_root / "multiwebcam" / "src" / "PySide6"
        if pyside is not None:
            try:
                from PySide6.QtCore import qVersion

                qt_version = qVersion()
            except Exception:
                qt_version = "未知"
            return DiagnosticCheck(
                "Qt 绑定",
                DiagnosticStatus.PASS,
                "PySide6 API 可用（Qt {}）".format(qt_version),
                str(pyside.origin or ""),
            )
        if bundled_shim.is_dir() and pyqt is not None:
            return DiagnosticCheck(
                "Qt 绑定",
                DiagnosticStatus.PASS,
                "Jetson PySide6 兼容层可用",
                str(bundled_shim),
            )
        return DiagnosticCheck(
            "Qt 绑定",
            DiagnosticStatus.FAILURE,
            "未发现 PySide6 或 Jetson 兼容层",
            "GUI 启动需要 PySide6 API 运行时。",
        )

    def _workspace_check(self) -> DiagnosticCheck:
        required = ("multiwebcam", "Tx_Rx", "3DGSviewer")
        missing = [name for name in required if not (self.paths.project_root / name).is_dir()]
        if not missing:
            return DiagnosticCheck(
                "项目工作区",
                DiagnosticStatus.PASS,
                "三个子项目均可定位",
                str(self.paths.project_root),
            )
        return DiagnosticCheck(
            "项目工作区",
            DiagnosticStatus.WARNING,
            "部分源码模块未安装或不可见",
            "缺少: " + ", ".join(missing),
        )

    def _opencv_check(self) -> DiagnosticCheck:
        try:
            import cv2

            build = cv2.getBuildInformation()
            has_gstreamer = any(
                line.strip().startswith("GStreamer:")
                and "YES" in line.upper()
                for line in build.splitlines()
            )
            detail = "{} · {}".format(cv2.__file__, "GStreamer=YES" if has_gstreamer else "GStreamer=NO")
            return DiagnosticCheck(
                "OpenCV / GStreamer",
                DiagnosticStatus.PASS if has_gstreamer else DiagnosticStatus.FAILURE,
                "OpenCV {}，GStreamer {}".format(
                    cv2.__version__, "可用" if has_gstreamer else "不可用"
                ),
                detail,
            )
        except Exception as exc:
            return DiagnosticCheck(
                "OpenCV / GStreamer",
                DiagnosticStatus.FAILURE,
                "OpenCV 无法导入",
                str(exc),
            )

    def _graphics_check(self) -> DiagnosticCheck:
        gl = ctypes.util.find_library("GL")
        egl = ctypes.util.find_library("EGL")
        plugin_path = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH", "")
        available = bool(gl and egl)
        detail = "GL={} · EGL={} · Qt平台插件={}".format(
            gl or "未发现",
            egl or "未发现",
            plugin_path or "由 Qt 自动发现",
        )
        return DiagnosticCheck(
            "OpenGL / EGL",
            DiagnosticStatus.PASS if available else DiagnosticStatus.WARNING,
            "原生图形库可定位" if available else "原生图形库不完整",
            detail,
        )

    def _camera_check(self) -> DiagnosticCheck:
        devices = sorted(Path("/dev").glob("video*"))
        if devices:
            return DiagnosticCheck(
                "摄像头",
                DiagnosticStatus.PASS,
                "发现 {} 个视频设备".format(len(devices)),
                ", ".join(str(device) for device in devices),
            )
        return DiagnosticCheck(
            "摄像头",
            DiagnosticStatus.WARNING,
            "未发现视频设备",
            "不影响应用外壳启动；进入采集时再连接设备。",
        )

    def _wsl_check(self) -> DiagnosticCheck:
        if self.settings.wsl_service_url:
            return DiagnosticCheck(
                "WSL 重建服务",
                DiagnosticStatus.WARNING,
                "已配置但尚未执行在线健康检查",
                self.settings.wsl_service_url,
            )
        return DiagnosticCheck(
            "WSL 重建服务",
            DiagnosticStatus.WARNING,
            "尚未配置服务地址",
            "可在“设置”页面填写；不影响离线启动。",
        )

    def _viewer_check(self) -> DiagnosticCheck:
        root = Path(self.settings.viewer_root)
        status = DiagnosticStatus.PASS if root.is_dir() else DiagnosticStatus.WARNING
        summary = "q3dviewer 源码可定位" if root.is_dir() else "q3dviewer 路径不可用"
        return DiagnosticCheck("结果查看器", status, summary, str(root))

    def _configuration_check(self) -> DiagnosticCheck:
        return DiagnosticCheck(
            "统一配置",
            DiagnosticStatus.PASS,
            "配置已加载",
            str(self.paths.config_file),
        )

    def _log_check(self) -> DiagnosticCheck:
        available = self.paths.log_dir.is_dir() and os.access(
            str(self.paths.log_dir), os.W_OK
        )
        return DiagnosticCheck(
            "统一日志",
            DiagnosticStatus.PASS if available else DiagnosticStatus.FAILURE,
            "日志目录可写" if available else "日志目录不可写",
            str(self.paths.log_file),
        )


def report_as_dict(report: DiagnosticReport) -> Dict[str, Any]:
    return {
        "usable": report.is_usable,
        "failures": report.failure_count,
        "warnings": report.warning_count,
        "checks": [
            {
                "name": check.name,
                "status": check.status.value,
                "summary": check.summary,
                "detail": check.detail,
            }
            for check in report.checks
        ],
    }


def render_report(report: DiagnosticReport, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(report_as_dict(report), ensure_ascii=False, indent=2)
    symbols = {
        DiagnosticStatus.PASS: "[通过]",
        DiagnosticStatus.WARNING: "[提示]",
        DiagnosticStatus.FAILURE: "[失败]",
    }
    lines: List[str] = ["Camera System 环境诊断"]
    for check in report.checks:
        line = "{} {}: {}".format(symbols[check.status], check.name, check.summary)
        lines.append(line)
        if check.detail:
            lines.append("  " + check.detail)
    lines.append(
        "汇总: {} 个失败，{} 个提示".format(
            report.failure_count,
            report.warning_count,
        )
    )
    return "\n".join(lines)
