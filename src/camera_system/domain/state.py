"""Workflow state machine shared by the three application components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet


class TaskState(str, Enum):
    """Local application state, independent of remote Tx_Rx status values."""

    IDLE = "idle"
    CAPTURING = "capturing"
    READY = "ready"
    UPLOADING = "uploading"
    RECONSTRUCTING = "reconstructing"
    DOWNLOADING = "downloading"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TRANSITIONS: Dict[TaskState, FrozenSet[TaskState]] = {
    TaskState.IDLE: frozenset(
        {TaskState.CAPTURING, TaskState.READY, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.CAPTURING: frozenset(
        {TaskState.READY, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.READY: frozenset(
        {TaskState.CAPTURING, TaskState.UPLOADING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.UPLOADING: frozenset(
        {TaskState.RECONSTRUCTING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.RECONSTRUCTING: frozenset(
        {TaskState.DOWNLOADING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.DOWNLOADING: frozenset(
        {TaskState.FINISHED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.FINISHED: frozenset({TaskState.IDLE}),
    TaskState.FAILED: frozenset({TaskState.IDLE}),
    TaskState.CANCELLED: frozenset({TaskState.IDLE}),
}


class StateTransitionError(ValueError):
    """Raised when a workflow attempts an invalid state transition."""


@dataclass(frozen=True)
class TaskStateMachine:
    """Immutable state machine so service calls cannot mutate UI objects."""

    state: TaskState = TaskState.IDLE

    def can_transition(self, target: TaskState) -> bool:
        """Return whether ``target`` is a valid next state."""

        return target in _TRANSITIONS[self.state]

    def transition(self, target: TaskState) -> "TaskStateMachine":
        """Return a new state machine after validating the transition."""

        target = TaskState(target)
        if not self.can_transition(target):
            raise StateTransitionError(f"invalid task state transition: {self.state.value} -> {target.value}")
        return TaskStateMachine(target)

    @property
    def terminal(self) -> bool:
        """Whether the state requires an explicit reset before reuse."""

        return self.state in {
            TaskState.FINISHED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
