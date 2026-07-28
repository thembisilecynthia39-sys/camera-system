"""Top-level application pages."""

from camera_system_app.ui.pages.capture_workspace import CaptureWorkspacePage
from camera_system_app.ui.pages.diagnostics_log import DiagnosticsLogPage
from camera_system_app.ui.pages.history import HistoryPage
from camera_system_app.ui.pages.result_viewer import ResultViewerPage
from camera_system_app.ui.pages.settings import SettingsPage
from camera_system_app.ui.pages.transfer_reconstruction import TransferReconstructionPage

__all__ = [
    "CaptureWorkspacePage",
    "DiagnosticsLogPage",
    "HistoryPage",
    "ResultViewerPage",
    "SettingsPage",
    "TransferReconstructionPage",
]

