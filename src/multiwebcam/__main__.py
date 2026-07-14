"""Entry point for multiwebcam application.

Usage:
    multiwebcam    # or 'mwc' for short
    python -m multiwebcam

Launches the application using the current directory as the project path.
If multiwebcam.toml exists, loads camera profiles from it.
If not, creates it when cameras are discovered.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from multiwebcam.ui import MainWindow


def main() -> None:
    """Launch multiwebcam application.

    Uses current working directory as project path.
    """
    os.environ.setdefault("QT_OPENGL", "desktop")
    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "xcb_glx")
    os.environ.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
    os.environ.setdefault("RESOURCE_NAME", "multiwebcam")
    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface_format.setVersion(4, 3)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(surface_format)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)

    QApplication.setApplicationName("multiwebcam")
    QApplication.setOrganizationName("multiwebcam")
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("边端 3DGS 重建")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("multiwebcam")
    app.setStyle("Fusion")

    # Use current directory as project path
    project_path = Path.cwd()

    # Log what we're doing
    toml_path = project_path / "multiwebcam.toml"
    if toml_path.exists():
        print(f"Loading project from: {project_path}")
    else:
        print(f"New project in: {project_path}")
        print("  Camera profiles will be saved to multiwebcam.toml")

    window = MainWindow(project_path)
    window.setWindowTitle(f"边端 3DGS 重建 · {project_path.name}")
    # This is a dense multi-camera workstation. Start maximized so the first
    # frame uses the same information hierarchy as the supported desktop
    # resolutions instead of squeezing four feeds into a 1200 px window.
    window.resize(1600, 900)
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
