import pytest

from camera_system.domain import StateTransitionError, TaskState, TaskStateMachine


def test_required_states_are_stable_wire_values():
    assert [state.value for state in TaskState] == [
        "idle",
        "capturing",
        "ready",
        "uploading",
        "reconstructing",
        "downloading",
        "finished",
        "failed",
        "cancelled",
    ]


def test_happy_path_covers_capture_upload_reconstruction_download():
    machine = TaskStateMachine()
    for state in (
        TaskState.CAPTURING,
        TaskState.READY,
        TaskState.UPLOADING,
        TaskState.RECONSTRUCTING,
        TaskState.DOWNLOADING,
        TaskState.FINISHED,
        TaskState.IDLE,
    ):
        machine = machine.transition(state)

    assert machine.state is TaskState.IDLE
    assert machine.terminal is False


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TaskState.IDLE, TaskState.FINISHED),
        (TaskState.CAPTURING, TaskState.DOWNLOADING),
        (TaskState.UPLOADING, TaskState.FINISHED),
        (TaskState.FINISHED, TaskState.RECONSTRUCTING),
    ],
)
def test_invalid_transitions_are_rejected(source, target):
    with pytest.raises(StateTransitionError):
        TaskStateMachine(source).transition(target)


@pytest.mark.parametrize("terminal", [TaskState.FAILED, TaskState.CANCELLED])
def test_failed_and_cancelled_tasks_can_be_reset(terminal):
    machine = TaskStateMachine(TaskState.IDLE).transition(TaskState.CAPTURING).transition(terminal)

    assert machine.terminal is True
    assert machine.transition(TaskState.IDLE).state is TaskState.IDLE
