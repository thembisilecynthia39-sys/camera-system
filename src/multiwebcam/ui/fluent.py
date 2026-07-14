"""Optional PyQt-Fluent-Widgets integration.

The Jetson runtime for this project uses a small PySide6 compatibility layer
backed by the system PyQt5 package. Recent qfluentwidgets releases assume a
newer PyQt5 surface than JetPack 5 provides, so this module patches only the
missing import-time symbols we need and falls back to stock Qt widgets when the
Fluent package is unavailable.
"""

from __future__ import annotations

import contextlib
import io
import sys
import types
from typing import Any

from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QPushButton, QWidget

from multiwebcam.ui.components import GuardedComboBox
from multiwebcam.ui.theme import Palette

_qfluentwidgets: Any | None = None
_load_error: Exception | None = None


def fluent_available() -> bool:
    """Return True when qfluentwidgets can be imported in this runtime."""
    return _load_qfluentwidgets() is not None


def fluent_error() -> Exception | None:
    """Return the last qfluentwidgets import error, if any."""
    _load_qfluentwidgets()
    return _load_error


def apply_fluent_theme() -> bool:
    """Apply Fluent theme tokens when qfluentwidgets is available."""
    qfw = _load_qfluentwidgets()
    if qfw is None:
        return False

    try:
        qfw.setTheme(qfw.Theme.DARK)
        qfw.setThemeColor(Palette.INTERACTIVE)
    except Exception as exc:  # pragma: no cover - defensive against external package changes
        global _load_error
        _load_error = exc
        return False
    return True


def push_button(text: str = "", parent: QWidget | None = None, *, primary: bool = False) -> QPushButton:
    """Create a native button styled by the application's workstation theme."""
    return QPushButton(text, parent)


def line_edit(text: str = "", parent: QWidget | None = None) -> QLineEdit:
    """Create a native line edit styled by the application theme."""
    widget = QLineEdit(parent)
    if text:
        widget.setText(text)
    return widget


def combo_box(parent: QWidget | None = None) -> QComboBox:
    """Create a native combo box for consistent cross-version behaviour."""
    return GuardedComboBox(parent)


def check_box(text: str = "", parent: QWidget | None = None) -> QCheckBox:
    """Create a native check box styled by the application theme."""
    return QCheckBox(text, parent)


def _load_qfluentwidgets() -> Any | None:
    global _qfluentwidgets, _load_error
    if _qfluentwidgets is not None:
        return _qfluentwidgets
    if _load_error is not None:
        return None

    try:
        _install_pyqt5_compat()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            import qfluentwidgets as qfw
    except Exception as exc:
        _load_error = exc
        return None

    _qfluentwidgets = qfw
    return _qfluentwidgets


def _install_pyqt5_compat() -> None:
    """Patch import-time gaps in Ubuntu 20.04's PyQt5 package."""
    try:
        import sip
    except Exception:
        sip = None
    if sip is not None:
        sys.modules.setdefault("PyQt5.sip", sip)

    try:
        from PyQt5 import QtCore
    except Exception:
        return
    try:
        from PyQt5 import QtGui
    except Exception:
        QtGui = None

    if not hasattr(QtCore, "QCalendar"):

        class QCalendar:
            class System:
                Gregorian = 0

            def __init__(self, *args, **kwargs) -> None:
                pass

        QtCore.QCalendar = QCalendar

    if QtGui is not None and not hasattr(QtGui.QFont, "setFamilies"):

        def set_families(self, families) -> None:
            if families:
                self.setFamily(families[0])

        QtGui.QFont.setFamilies = set_families

    if QtGui is not None and not hasattr(QtGui.QFont, "families"):

        def families(self) -> list[str]:
            family = self.family()
            return [family] if family else []

        QtGui.QFont.families = families

    if "PyQt5.QtX11Extras" not in sys.modules:
        qt_x11_extras = types.ModuleType("PyQt5.QtX11Extras")

        class QX11Info:
            @staticmethod
            def isPlatformX11() -> bool:
                return False

            @staticmethod
            def connection():
                return None

            @staticmethod
            def appRootWindow(screen=None) -> int:
                return 0

            @staticmethod
            def appScreen() -> int:
                return 0

        qt_x11_extras.QX11Info = QX11Info
        sys.modules["PyQt5.QtX11Extras"] = qt_x11_extras
