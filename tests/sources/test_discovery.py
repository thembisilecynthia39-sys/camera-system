from pathlib import Path

from multiwebcam.sources.discovery import FrameSourceOptions, VideoMode, discover_frame_sources


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
        lambda path: options_by_path[path],
    )

    discovered = discover_frame_sources()

    assert [options.path for options in discovered] == ["/dev/video0", "/dev/video2"]
