"""Application composition root with lazy Qt loading."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Optional

from camera_system_app.application.controller import ApplicationController
from camera_system_app.config.settings import AppSettings, SettingsManager
from camera_system_app.infrastructure.logging import LogService, configure_logging
from camera_system_app.infrastructure.paths import AppPaths


@dataclass
class AppContext:
    paths: AppPaths
    settings_manager: SettingsManager
    settings: AppSettings
    logs: LogService


def build_context(
    project_root: Optional[str] = None,
    config_file: Optional[str] = None,
) -> AppContext:
    """Build all Qt-independent application services."""

    paths = AppPaths.discover(project_root=project_root, config_file=config_file)
    paths.prepare_runtime_directories()
    settings_manager = SettingsManager(paths)
    settings = settings_manager.load()
    logs = configure_logging(paths.log_file, settings.log_level)
    logger = logging.getLogger("camera_system_app.bootstrap")
    if settings_manager.last_error:
        logger.warning(
            "Invalid settings file; defaults are active: %s",
            settings_manager.last_error,
        )
    logger.info("Application context initialized for %s", paths.project_root)
    return AppContext(paths, settings_manager, settings, logs)


def _ensure_qt_api(paths: AppPaths) -> None:
    """Expose the verified Jetson compatibility layer when PySide6 is absent."""

    multiwebcam_root = paths.project_root / "multiwebcam"
    multiwebcam_source = multiwebcam_root / "src"
    jetson_site_packages = (
        multiwebcam_root
        / ".venv-jetson"
        / "lib"
        / "python{}.{}".format(sys.version_info.major, sys.version_info.minor)
        / "site-packages"
    )
    if jetson_site_packages.is_dir() and str(jetson_site_packages) not in sys.path:
        sys.path.insert(0, str(jetson_site_packages))
    if multiwebcam_source.is_dir() and str(multiwebcam_source) not in sys.path:
        sys.path.insert(0, str(multiwebcam_source))
    if importlib.util.find_spec("PySide6") is not None:
        return
    shim_parent = multiwebcam_source
    if (shim_parent / "PySide6").is_dir():
        sys.path.insert(0, str(shim_parent))


def run_gui(
    context: AppContext,
    smoke_test_ms: Optional[int] = None,
    force_windowed: bool = False,
) -> int:
    """Create and run the Qt shell without initializing optional hardware."""

    _ensure_qt_api(context.paths)
    os.environ.setdefault("RESOURCE_NAME", "camera-system")
    os.environ["Q3D_QT_IMPL"] = "PySide6"
    os.environ.setdefault("QT_OPENGL", "desktop")

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWidgets import QMessageBox

    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.OpenGL)
    surface_format.setVersion(4, 3)
    surface_format.setProfile(QSurfaceFormat.CoreProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(surface_format)

    from camera_system_app.ui.bindings import ApplicationBindings
    from camera_system_app.ui.capture_bindings import CaptureBindings
    from camera_system_app.ui.main_window import MainWindow
    from camera_system_app.ui.reconstruction_bindings import ReconstructionBindings
    from camera_system_app.ui.viewer_bindings import ViewerBindings
    from camera_system_app.ui.theme import application_stylesheet
    from camera_system_app.infrastructure.adapters import MultiWebcamCaptureAdapter
    from camera_system_app.application.reconstruction_service import ReconstructionWorkflow
    from camera_system_app.infrastructure.reconstruction_repository import (
        ReconstructionJobRepository,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("camera-system")
    app.setOrganizationName("camera-system")
    app.setApplicationDisplayName("边端 3DGS 重建")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("camera-system")
    app.setStyle("Fusion")
    app.setStyleSheet(application_stylesheet())
    instance_lock = QLockFile(str(context.paths.state_dir / "camera-system.lock"))
    instance_lock.setStaleLockTime(10000)
    if not instance_lock.tryLock(0):
        QMessageBox.warning(
            None,
            "应用已在运行",
            "Camera System 已有一个实例正在运行，请切换到现有窗口。",
        )
        return 3

    controller = ApplicationController(
        context.paths,
        context.settings_manager,
        context.settings,
        context.logs,
    )
    window = MainWindow(context.paths, context.settings)
    window._instance_lock = instance_lock
    logger = logging.getLogger("camera_system_app.bootstrap")

    def handle_uncaught(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Uncaught UI exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        QMessageBox.critical(
            window,
            "应用发生错误",
            "操作未能完成，但应用仍可继续使用。\n{}".format(exc_value),
        )

    sys.excepthook = handle_uncaught
    bindings = ApplicationBindings(window, controller, window)
    bindings.initialize()
    window._application_bindings = bindings
    repository = ReconstructionJobRepository(
        context.paths.data_dir / "tasks",
        legacy_root=context.paths.state_dir / "reconstruction_tasks",
    )
    reconstruction_workflow = ReconstructionWorkflow(
        context.paths.project_root,
        context.settings,
        repository,
    )
    reconstruction_bindings = ReconstructionBindings(
        window, reconstruction_workflow, context.settings_manager, window
    )
    reconstruction_bindings.initialize()
    window._reconstruction_bindings = reconstruction_bindings
    viewer_bindings = ViewerBindings(window, context.paths.project_root, window)
    window._viewer_bindings = viewer_bindings
    managed_components = [reconstruction_bindings, viewer_bindings]
    if smoke_test_ms is not None:
        # The hidden smoke path verifies that the shell can construct and close
        # without optional hardware.  Starting discovery here races a 100 ms
        # test shutdown against V4L2 and can crash inside a native backend.
        from camera_system_app.domain import CaptureRuntimeState, CaptureRuntimeStatus

        window.capture_page.set_runtime_state(
            CaptureRuntimeState(
                CaptureRuntimeStatus.STOPPED,
                "界面冒烟测试：未初始化摄像头",
            )
        )
    else:
        try:
            capture_adapter = MultiWebcamCaptureAdapter(
                context.paths.project_root,
                parent=window,
            )
        except Exception as exc:
            logging.getLogger("camera_system_app.bootstrap").exception(
                "multiwebcam capture service is unavailable"
            )
            from camera_system_app.domain import CaptureRuntimeState, CaptureRuntimeStatus

            window.capture_page.set_runtime_state(
                CaptureRuntimeState(
                    CaptureRuntimeStatus.UNAVAILABLE,
                    "采集服务不可用：{}".format(exc),
                )
            )
        else:
            capture_bindings = CaptureBindings(
                window,
                controller,
                capture_adapter,
                reconstruction_bindings.register_capture,
                window,
            )
            capture_bindings.initialize()
            window._capture_bindings = capture_bindings
            managed_components.append(capture_bindings)

    from camera_system_app.ui.lifecycle import LifecycleCoordinator

    lifecycle = LifecycleCoordinator(window, managed_components, window)
    app.aboutToQuit.connect(lifecycle.shutdown)
    window._lifecycle = lifecycle

    if context.settings.start_maximized and not force_windowed:
        window.showMaximized()
    else:
        window.show()
    if smoke_test_ms is not None:
        # Exercise the same coordinated window-close path as a real user.  A
        # direct QApplication.quit() can destroy PyQt5 widgets while the
        # lifecycle event filter is still scheduling its deferred close.
        QTimer.singleShot(max(1, smoke_test_ms), window.close)
    return int(app.exec())
