import subprocess
from pathlib import Path

import pytest

from multiwebcam.sources import discovery as discovery_module
from multiwebcam.sources.discovery import (
    FrameSourceOptions,
    VideoMode,
    discover_frame_sources,
    usb_root_bus,
)


def test_usb_root_bus_strips_nested_port_segments():
    assert usb_root_bus("usb-3610000.xhci-2.1.1.4") == "usb-3610000.xhci-2"
    assert usb_root_bus("usb-0000:00:14.0-3.1") == "usb-0000:00:14.0-3"
    assert usb_root_bus("platform-camera") == "platform-camera"


def test_discovery_deduplicates_multiple_video_nodes_for_same_bus(monkeypatch):
    paths = [Path("/dev/video0"), Path("/dev/video1"), Path("/dev/video2")]
    options_by_path = {
        "/dev/video0": FrameSourceOptions(
            path="/dev/video0",
            model="Camera A",
            driver="uvcvideo",
            bus_info="usb-a",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
        "/dev/video1": FrameSourceOptions(
            path="/dev/video1",
            model="Camera A duplicate",
            driver="uvcvideo",
            bus_info="usb-a",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
        "/dev/video2": FrameSourceOptions(
            path="/dev/video2",
            model="Camera B",
            driver="uvcvideo",
            bus_info="usb-b",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
    }

    monkeypatch.setattr(Path, "glob", lambda self, pattern: paths if str(self) == "/dev" else [])
    monkeypatch.setattr(
        "multiwebcam.sources.discovery.get_frame_source_options",
        lambda path, **_kwargs: options_by_path[path],
    )

    discovered = discover_frame_sources()

    assert [options.path for options in discovered] == ["/dev/video0", "/dev/video2"]


def test_v4l2_command_terminates_and_reaps_process_when_cancelled(monkeypatch):
    class Process:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self.communicated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def communicate(self, timeout=None):
            self.communicated = True
            return ("", "")

    process = Process()
    monkeypatch.setattr(
        discovery_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )
    checks = iter((False, True))

    with pytest.raises(InterruptedError, match="cancel"):
        discovery_module._run_command(
            ["v4l2-ctl", "--info"],
            timeout=5.0,
            cancel_check=lambda: next(checks, True),
        )

    assert process.terminated
    assert not process.killed
    assert process.communicated


def test_v4l2_command_kills_process_that_survives_timeout(monkeypatch):
    class Process:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self.communicated = 0

        def poll(self):
            return 0 if self.killed else None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def communicate(self, timeout=None):
            self.communicated += 1
            if timeout is not None and not self.killed:
                raise subprocess.TimeoutExpired("v4l2-ctl", timeout)
            return ("", "")

    process = Process()
    monkeypatch.setattr(
        discovery_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )

    with pytest.raises(subprocess.TimeoutExpired):
        discovery_module._run_command(
            ["v4l2-ctl", "--list-formats-ext"],
            timeout=0.0,
        )

    assert process.terminated
    assert process.killed
    assert process.communicated == 2
