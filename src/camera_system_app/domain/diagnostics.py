"""Qt-independent environment diagnostic values."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Tuple


class DiagnosticStatus(str, Enum):
    """Severity of one diagnostic check."""

    PASS = "pass"
    WARNING = "warning"
    FAILURE = "failure"


@dataclass(frozen=True)
class DiagnosticCheck:
    """One named environment check."""

    name: str
    status: DiagnosticStatus
    summary: str
    detail: str = ""


@dataclass(frozen=True)
class DiagnosticReport:
    """A point-in-time collection of environment checks."""

    checks: Tuple[DiagnosticCheck, ...]

    @classmethod
    def from_checks(cls, checks: Iterable[DiagnosticCheck]) -> "DiagnosticReport":
        return cls(tuple(checks))

    @property
    def failure_count(self) -> int:
        return sum(check.status is DiagnosticStatus.FAILURE for check in self.checks)

    @property
    def warning_count(self) -> int:
        return sum(check.status is DiagnosticStatus.WARNING for check in self.checks)

    @property
    def is_usable(self) -> bool:
        return self.failure_count == 0

