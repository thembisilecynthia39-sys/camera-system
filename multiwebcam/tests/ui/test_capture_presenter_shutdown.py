from types import SimpleNamespace

import pytest

from multiwebcam.ui.presenters import capture as capture_module
from multiwebcam.ui.presenters.capture import CapturePresenter


def test_shutdown_shares_one_deadline_across_background_workers(monkeypatch):
    now = 100.0
    received_timeouts = []

    def monotonic():
        return now

    class Worker:
        def stop(self, timeout):
            nonlocal now
            received_timeouts.append(timeout)
            now += 0.02
            return True

    monkeypatch.setattr(capture_module.time, "monotonic", monotonic)
    monkeypatch.setattr(
        CapturePresenter,
        "_start_detector_initialization",
        lambda _self: None,
    )
    session = SimpleNamespace(
        is_recording=False,
        has_pending_recording=False,
    )
    presenter = CapturePresenter(session, {})
    presenter._preview_worker = Worker()
    presenter._quality_worker = Worker()
    presenter._control_worker = Worker()

    assert presenter.shutdown(timeout_ms=60)

    assert received_timeouts[0] == pytest.approx(0.06)
    assert 0.039 <= received_timeouts[1] <= 0.041
    assert 0.019 <= received_timeouts[2] <= 0.021
