"""Qt fixtures for capture-adapter tests."""

import os

import pytest


if os.environ.get("CAMERA_SYSTEM_HARDWARE_GL_TEST") != "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
