"""Shared Qt application lifetime for every UI test module."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def ui_qapplication():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
