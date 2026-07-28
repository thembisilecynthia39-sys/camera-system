from camera_system import CaptureService, ReconstructionService, TransferService, ViewerService
from camera_system.adapters import Q3DViewerAdapter


def test_protocols_are_importable_without_qt():
    assert CaptureService is not None
    assert ReconstructionService is not None
    assert TransferService is not None
    assert ViewerService is not None


def test_viewer_adapter_has_a_qt_free_format_port():
    formats = Q3DViewerAdapter().supported_formats()

    assert ".ply" in formats
    assert ".npy" in formats
