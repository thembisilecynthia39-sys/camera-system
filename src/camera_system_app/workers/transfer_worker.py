"""Qt thread boundary for the complete Tx_Rx workflow."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from camera_system_app.domain import normalize_error


class TransferWorker(QThread):
    job_changed = Signal(object)
    upload_progress = Signal(int, int)
    reconstruction_progress = Signal(float, str)
    download_progress = Signal(int, int)
    result_available = Signal(object)
    failed = Signal(object)

    def __init__(self, workflow, job_id: str, parent=None) -> None:
        super().__init__(parent)
        self.workflow = workflow
        self.job_id = job_id
        self._session = None

    def run(self) -> None:
        from tx_rx.jetson_client.http_client import direct_session

        session = direct_session(max_retries=0)
        self._session = session
        try:
            event = self.workflow.execute(
                self.job_id,
                job_callback=self.job_changed.emit,
                upload_callback=self.upload_progress.emit,
                reconstruction_callback=self.reconstruction_progress.emit,
                download_callback=self.download_progress.emit,
                cancel_check=self.isInterruptionRequested,
                session=session,
            )
        except Exception as exc:
            self.failed.emit(normalize_error(exc, "传输与重建"))
            return
        finally:
            session.close()
            self._session = None
        self.result_available.emit(event)

    def cancel(self) -> None:
        self.requestInterruption()
        session = self._session
        if session is not None:
            session.close()
