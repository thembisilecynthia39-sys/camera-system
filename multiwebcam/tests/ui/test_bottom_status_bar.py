from PySide6.QtWidgets import QApplication, QLabel

from multiwebcam.ui.components import BottomStatusBar


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _label_texts(widget: BottomStatusBar) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel)]


def test_bottom_status_bar_shows_two_user_endpoints():
    app = _app()
    status = BottomStatusBar()

    assert app is not None
    assert "WSL  --" in _label_texts(status)
    assert "Jetson  --" in _label_texts(status)


def test_bottom_status_bar_updates_each_endpoint_ping():
    app = _app()
    status = BottomStatusBar()

    status.set_client_ping(1, 24.6)
    status.set_client_ping(2, None)

    texts = _label_texts(status)
    assert app is not None
    assert "WSL  25 ms" in texts
    assert "Jetson  离线" in texts
    assert status.client_one.property("state") == "good"
    assert status.client_two.property("state") == "bad"
