# Cancellation and Shutdown Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure upload, recording startup, and capture shutdown honor cancellation without leaving producers, encoders, or UI state active.

**Architecture:** Cancellation remains cooperative and flows from Qt's
`isInterruptionRequested` callback through the pure-Python Tx_Rx orchestration
to archive creation and HTTP streaming. Recording state becomes transactional:
the session publishes the recording flag only after encoder startup succeeds,
and capture shutdown always signals camera producers even when recording
finalization fails.

**Tech Stack:** Python 3.8, PySide6 compatibility shim, `requests`, Python
threads/events/queues, pytest.

## Global Constraints

- Jetson Orin Nano / JetPack 5.1.1 is the production acceptance environment.
- Preserve every pre-existing uncommitted worktree change.
- Write and observe a failing regression test before each production change.
- Do not add dependencies or perform unrelated refactors.
- A shutdown call has one shared deadline; failure is reported without skipping
  cleanup of independently owned resources.

---

### Task 1: Propagate cancellation through staged upload orchestration

**Files:**
- Modify: `Tx_Rx/tx_rx/jetson_client/uploader.py`
- Test: `Tx_Rx/tests/test_uploader.py`

**Interfaces:**
- Consumes: existing `CancelCheck = Callable[[], bool]` and
  `UploadProgressCallback = Callable[[int, int], None]`.
- Produces:
  `upload_staged_task(staging_dir, config_path=None, session=None,
  progress_callback=None, cancel_check=None) -> TaskUploadResult`.
- Produces:
  `request_reconstruction(package, task_id, config, session=None,
  cancel_check=None) -> ReconstructResponse`.

- [ ] **Step 1: Write a failing cancellation test**

Add a test that cancels before the health request and proves no network method
is called:

```python
def test_staged_upload_honors_cancellation_before_network(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")
    session = _Session()

    with pytest.raises(TaskUploadError, match="upload cancelled"):
        upload_staged_task(
            staging_dir,
            config,
            session,
            cancel_check=lambda: True,
        )

    assert session.calls == []
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  Tx_Rx/tests/test_uploader.py::test_staged_upload_honors_cancellation_before_network
```

Expected: FAIL because `upload_staged_task` does not accept `cancel_check`.

- [ ] **Step 3: Write a failing pre-reconstruction cancellation test**

Use a session whose `/upload` response is valid and whose upload handler flips
the cancel callback before `/reconstruct`. Assert that only health and upload
requests occurred and `TaskUploadError("upload cancelled")` is raised.

- [ ] **Step 4: Implement minimal cancellation propagation**

In `upload_staged_task`:

```python
def upload_staged_task(
    staging_dir: Path,
    config_path: Optional[Path] = None,
    session: Optional[Any] = None,
    progress_callback: Optional[UploadProgressCallback] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> TaskUploadResult:
    _check_cancel(cancel_check)
    package = load_staged_task_package(staging_dir)
    _check_cancel(cancel_check)
    config = load_config(config_path)
    client = session or direct_session()
    check_health(config, client, cancel_check=cancel_check)
    upload_response = upload_task_package(
        package,
        config,
        client,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    _check_cancel(cancel_check)
    reconstruct_response = request_reconstruction(
        package,
        upload_response.task_id,
        config,
        client,
        cancel_check=cancel_check,
    )
```

In `request_reconstruction`, call `_check_cancel(cancel_check)` immediately
before the idempotent-key POST. Once the server has responded, validate and
return that response so the client does not discard a known remote outcome.

- [ ] **Step 5: Run uploader tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q Tx_Rx/tests/test_uploader.py
```

Expected: all uploader tests pass.

- [ ] **Step 6: Commit the task**

```bash
git add Tx_Rx/tx_rx/jetson_client/uploader.py Tx_Rx/tests/test_uploader.py
git commit -m "fix: propagate upload cancellation"
```

### Task 2: Connect Qt worker interruption to upload cancellation

**Files:**
- Modify: `multiwebcam/src/multiwebcam/ui/coordinator.py`
- Create: `multiwebcam/tests/ui/test_transfer_cancellation.py`

**Interfaces:**
- Consumes: the Task 1 `upload_staged_task(..., progress_callback,
  cancel_check)` interface.
- Produces: `_CaptureTransferWorker` and `_StagedUploadWorker` that stop at
  task boundaries, during archive construction, and during multipart upload
  when `requestInterruption()` is called.

- [ ] **Step 1: Write a failing selected-transfer worker test**

Monkeypatch the lazily imported Tx_Rx functions. The fake
`upload_staged_task` requests interruption on the worker, evaluates the
received `cancel_check`, and raises `TaskUploadError("upload cancelled")`.
Run `worker.run()` directly and assert `transfer_completed` emits the literal
error `"upload cancelled"`. This must fail against the current worker because
it does not pass a cancellation callback.

- [ ] **Step 2: Write a failing staged-upload worker test**

Create two task paths. The first fake upload requests interruption; assert the
second path is never uploaded and the worker reports cancellation instead of
continuing the batch.

- [ ] **Step 3: Run both tests and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  multiwebcam/tests/ui/test_transfer_cancellation.py
```

Expected: both tests fail because worker interruption is not propagated.

- [ ] **Step 4: Implement worker cancellation**

Pass `cancel_check=self.isInterruptionRequested` to every
`upload_staged_task` call. In `_StagedUploadWorker`, check
`isInterruptionRequested()` before each task and stop the loop after a
`TaskUploadError` caused by cancellation. In `_CaptureTransferWorker`, also
check interruption before metadata fetch and ACK so no new protocol stage
starts after cancellation.

- [ ] **Step 5: Run worker and protocol tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  multiwebcam/tests/ui/test_transfer_cancellation.py \
  Tx_Rx/tests/test_uploader.py \
  Tx_Rx/tests/test_http_protocol.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit the task**

```bash
git add multiwebcam/src/multiwebcam/ui/coordinator.py \
  multiwebcam/tests/ui/test_transfer_cancellation.py
git commit -m "fix: cancel Qt transfer workers"
```

### Task 3: Roll back recording state when encoder startup fails

**Files:**
- Modify: `multiwebcam/src/multiwebcam/pipeline/session.py`
- Create: `multiwebcam/tests/recording/test_session_recording_lifecycle.py`

**Interfaces:**
- Consumes: existing `FrameRecorder.start()` exception contract.
- Produces: `CaptureSession.start_recording(...)` that leaves
  `is_recording == False`, `has_pending_recording == False`, and no active
  recording device paths after startup failure.

- [ ] **Step 1: Write the failing transactional-start test**

Build a session with one bounded `QueueBundle`, monkeypatch `FrameRecorder`
with a fake whose `start()` raises `OSError("disk unavailable")`, then assert:

```python
with pytest.raises(OSError, match="disk unavailable"):
    session.start_recording(tmp_path, {"/dev/video0": 0})

assert not session.is_recording
assert not session.has_pending_recording
assert session._recording_device_paths == []
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  multiwebcam/tests/recording/test_session_recording_lifecycle.py::test_failed_recorder_start_rolls_back_session_state
```

Expected: FAIL because the current method leaves the flag and recorder set.

- [ ] **Step 3: Implement transactional publication**

Create the recorder in a local variable, start it, and only then publish
`self._frame_recorder`, `_recording_device_paths`, and `_is_recording` under
`_recording_gate`. On any exception, clear all three state values and re-raise.
Starting encoders before setting the producer flag is intentional: frames that
arrive during startup belong to preview, while no producer can fill an
unconsumed recording queue.

- [ ] **Step 4: Run recording tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  multiwebcam/tests/recording \
  multiwebcam/tests/pipeline/test_producer_backpressure.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit the task**

```bash
git add multiwebcam/src/multiwebcam/pipeline/session.py \
  multiwebcam/tests/recording/test_session_recording_lifecycle.py
git commit -m "fix: roll back failed recording startup"
```

### Task 4: Continue camera cleanup after recording drain failure

**Files:**
- Modify: `multiwebcam/src/multiwebcam/pipeline/session.py`
- Modify: `multiwebcam/tests/recording/test_session_recording_lifecycle.py`

**Interfaces:**
- Consumes: `FrameRecorder.stop(drain_timeout: float)` and producer
  `request_stop()/wait_stopped(timeout)` contracts.
- Produces:
  `CaptureSession.stop_recording(drain_timeout: float = 10.0) ->
  RecordingResult | None`.
- Produces: `CaptureSession.stop(timeout)` that always signals and joins all
  producers, returns `False` when recording finalization failed, and preserves
  the pending recorder for an explicit retry.

- [ ] **Step 1: Write the failing cleanup-after-drain-error test**

Use a fake recorder whose `stop()` raises
`RecordingDrainTimeout("encoder still running")` and a fake producer recording
whether `request_stop()` and `wait_stopped()` were called. Assert
`session.stop(timeout=0.1) is False`, both producer methods were called, and
`session.has_pending_recording` remains true.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  multiwebcam/tests/recording/test_session_recording_lifecycle.py::test_session_stop_releases_cameras_after_recording_drain_timeout
```

Expected: FAIL because the exception currently escapes before producer stop.

- [ ] **Step 3: Implement independent cleanup**

Wrap `stop_recording()` in `CaptureSession.stop()` and record failure without
returning early. Pass the remaining shared deadline to recording finalization,
stop the alignment monitor, signal every producer, then join every producer.
Return `False` if any independently owned component failed. Do not discard
`_frame_recorder` on drain timeout because its encoder threads may still need
to be joined on a later retry.

- [ ] **Step 4: Run lifecycle and capture tests**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  multiwebcam/tests/recording/test_session_recording_lifecycle.py \
  tests/app_shell/test_capture_service.py
```

Expected: all tests pass.

- [ ] **Step 5: Run full automated gate**

Run:

```bash
.venv-jetson/bin/python -m pytest -q
git diff --check
```

Expected: all automated tests pass; only the opt-in OpenGL hardware test may
be skipped.

- [ ] **Step 6: Run applicable Jetson diagnostics**

Run the non-destructive diagnostics:

```bash
./scripts/jetson/diagnose.sh
```

If cameras are available, run the repository's camera smoke command documented
by the diagnostic output. Record unavailable external WSL reconstruction as an
unverified external gate rather than treating local protocol tests as proof.

- [ ] **Step 7: Commit the task**

```bash
git add multiwebcam/src/multiwebcam/pipeline/session.py \
  multiwebcam/tests/recording/test_session_recording_lifecycle.py
git commit -m "fix: finish capture cleanup after recorder failure"
```
