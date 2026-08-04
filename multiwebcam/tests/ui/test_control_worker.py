from __future__ import annotations

from threading import Event

from PySide6.QtTest import QSignalSpy

from multiwebcam.ui.control_worker import CameraControlWorker


def test_control_worker_does_not_block_caller(monkeypatch):
    started = Event()
    release = Event()

    def slow_set(_device, _name, _value):
        started.set()
        assert release.wait(2.0)
        return True

    monkeypatch.setattr(
        "multiwebcam.ui.control_worker.set_control",
        slow_set,
    )
    worker = CameraControlWorker()
    applied = QSignalSpy(worker.control_applied)

    worker.set_value("/dev/video0", "exposure_absolute", 100)

    assert started.wait(1.0)
    release.set()
    assert applied.wait(2000)
    assert worker.stop()


def test_control_worker_coalesces_repeated_values(monkeypatch):
    first_started = Event()
    release_first = Event()
    latest_applied = Event()
    values = []

    def slow_set(_device, _name, value):
        values.append(value)
        if value == 1:
            first_started.set()
            assert release_first.wait(2.0)
        if value == 3:
            latest_applied.set()
        return True

    monkeypatch.setattr(
        "multiwebcam.ui.control_worker.set_control",
        slow_set,
    )
    worker = CameraControlWorker()
    worker.set_value("/dev/video0", "brightness", 1)
    assert first_started.wait(1.0)
    worker.set_value("/dev/video0", "brightness", 2)
    worker.set_value("/dev/video0", "brightness", 3)
    release_first.set()

    assert latest_applied.wait(2.0)
    assert worker.stop()
    assert values == [1, 3]
