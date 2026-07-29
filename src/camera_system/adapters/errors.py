"""Errors used at service boundaries."""

from __future__ import annotations

from typing import Optional

from ..domain import AppError


class ServiceError(RuntimeError):
    """Exception carrying a Qt-independent, serializable application error."""

    def __init__(self, error: AppError, cause: Optional[BaseException] = None) -> None:
        self.error = error
        self.cause = cause
        super().__init__(error.message)


def make_service_error(
    code: str,
    message: str,
    operation: str,
    exc: BaseException,
    *,
    recoverable: bool = False,
) -> ServiceError:
    """Convert an implementation exception without leaking it into domain data."""

    return ServiceError(
        AppError(
            code=code,
            message=message,
            operation=operation,
            recoverable=recoverable,
            details={"exception_type": type(exc).__name__},
        ),
        cause=exc,
    )
