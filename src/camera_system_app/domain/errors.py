"""Stable application error hierarchy with user-facing messages."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    PERSISTENCE = "persistence"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TIMEOUT = "timeout"
    REMOTE_FAILURE = "remote_failure"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    CAMERA_DISCONNECTED = "camera_disconnected"
    VIEWER_FAILURE = "viewer_failure"
    SHUTDOWN_FAILURE = "shutdown_failure"
    INTERNAL = "internal"


class ApplicationError(Exception):
    """Base error safe to log and present without exposing a traceback."""

    def __init__(
        self,
        code: ErrorCode,
        user_message: str,
        *,
        detail: str = "",
        recoverable: bool = True,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.detail = detail or user_message
        self.recoverable = recoverable
        super().__init__(self.detail)


class TaskValidationError(ApplicationError):
    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(
            ErrorCode.VALIDATION,
            message,
            detail=detail,
            recoverable=True,
        )


class TaskPersistenceError(ApplicationError):
    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(
            ErrorCode.PERSISTENCE,
            message,
            detail=detail,
            recoverable=False,
        )


class ServiceUnavailableError(ApplicationError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            ErrorCode.SERVICE_UNAVAILABLE,
            "WSL 重建服务已断开或无法连接，请检查地址、端口和服务状态后重试。",
            detail=detail,
            recoverable=True,
        )


class RemoteServiceError(ApplicationError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            ErrorCode.REMOTE_FAILURE,
            "WSL 重建服务返回错误，请查看日志或服务端状态后重试。",
            detail=detail,
            recoverable=True,
        )


class OperationTimeoutError(ApplicationError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            ErrorCode.TIMEOUT,
            "操作超时，请检查网络和 WSL 重建服务后重试。",
            detail=detail,
            recoverable=True,
        )


class OperationCancelledError(ApplicationError):
    def __init__(self, interrupted: bool = False, detail: str = "") -> None:
        super().__init__(
            ErrorCode.INTERRUPTED if interrupted else ErrorCode.CANCELLED,
            (
                "应用关闭前已安全中断传输；下次启动后可以继续重试。"
                if interrupted
                else "任务已取消，可以重新开始。"
            ),
            detail=detail,
            recoverable=True,
        )


class ShutdownError(ApplicationError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            ErrorCode.SHUTDOWN_FAILURE,
            "仍有后台任务未能安全停止，应用将保持打开，请稍后重试关闭。",
            detail=detail,
            recoverable=True,
        )


def normalize_error(exc: BaseException, context: str = "") -> ApplicationError:
    """Translate implementation exceptions into stable user-facing categories."""

    if isinstance(exc, ApplicationError):
        return exc
    detail = str(exc).strip() or type(exc).__name__
    exception_names = {
        type(item).__name__
        for item in _exception_chain(exc)
    }
    lowered = detail.lower()
    prefix = "{}: ".format(context) if context else ""
    if any(token in lowered for token in ("cancelled", "canceled")):
        return OperationCancelledError(detail=prefix + detail)
    if exception_names & {"Timeout", "TimeoutError", "ConnectTimeout", "ReadTimeout"} or any(
        token in lowered for token in ("timed out", "timeout")
    ):
        return OperationTimeoutError(prefix + detail)
    if exception_names & {"ConnectionError", "ProxyError"} or any(
        token in lowered
        for token in (
            "connection refused",
            "connection aborted",
            "connection reset",
            "failed to establish",
            "health check failed",
            "name or service not known",
            "network is unreachable",
            "remote end closed",
            "temporary failure in name resolution",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
        )
    ):
        return ServiceUnavailableError(prefix + detail)
    if "http " in lowered or "server error" in lowered:
        return RemoteServiceError(prefix + detail)
    return ApplicationError(
        ErrorCode.INTERNAL,
        "操作失败：{}".format(detail),
        detail=prefix + detail,
        recoverable=True,
    )


def _exception_chain(exc: BaseException):
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def user_message(exc: BaseException, context: str = "") -> str:
    return normalize_error(exc, context).user_message
