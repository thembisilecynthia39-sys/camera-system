"""Application-shell domain values."""

from camera_system_app.domain.capture import (
    CaptureCompletedEvent,
    CaptureRuntimeState,
    CaptureRuntimeStatus,
)
from camera_system_app.domain.diagnostics import (
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
)
from camera_system_app.domain.reconstruction import (
    ACTIVE_STATES,
    ReconstructionJob,
    ReconstructionState,
    ResultAvailableEvent,
)
from camera_system_app.domain.errors import (
    ApplicationError,
    ErrorCode,
    OperationCancelledError,
    OperationTimeoutError,
    RemoteServiceError,
    ServiceUnavailableError,
    ShutdownError,
    TaskPersistenceError,
    TaskValidationError,
    normalize_error,
    user_message,
)

__all__ = [
    "CaptureCompletedEvent",
    "CaptureRuntimeState",
    "CaptureRuntimeStatus",
    "DiagnosticCheck",
    "DiagnosticReport",
    "DiagnosticStatus",
    "ACTIVE_STATES",
    "ReconstructionJob",
    "ReconstructionState",
    "ResultAvailableEvent",
    "ApplicationError",
    "ErrorCode",
    "OperationCancelledError",
    "OperationTimeoutError",
    "RemoteServiceError",
    "ServiceUnavailableError",
    "ShutdownError",
    "TaskPersistenceError",
    "TaskValidationError",
    "normalize_error",
    "user_message",
]
