# Cancellation and Dependency Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make large-model loading, camera discovery, task packaging, and result transfer respond promptly to shutdown while documenting the real JetPack dependency boundary.

**Architecture:** Keep the existing thread and data-ownership model. Propagate optional cancellation callbacks into bounded CPU/file chunks, own V4L2 subprocesses so they can be terminated, and wrap HTTP timeout retries in one overall deadline. Validate only project-owned Jetson dependencies instead of treating unrelated system-site packages as application failures.

**Tech Stack:** Python 3.8, NumPy 1.23, Qt 5.12 through the PySide6 compatibility layer, requests 2.22/urllib3 1.25, OpenCV 4.5 with GStreamer, pytest.

## Global Constraints

- Jetson Orin Nano with JetPack 5.1.1 is the production acceptance target.
- Do not replace or upgrade JetPack's PyQt5, OpenCV, CUDA, TensorRT, `launchpadlib`, or `onnx-graphsurgeon`.
- Preserve atomic publication of staging tasks and downloaded PLY results.
- Cancellation must not be reported as a corrupt-file or protocol-validation failure.
- No generated files, environments, logs, captures, or result models may be committed.

---

### Task 1: Cancellable q3dviewer binary PLY conversion

**Files:**
- Modify: `3DGSviewer/q3dviewer/q3dviewer/utils/cloud_io.py`
- Modify: `src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py`
- Test: `tests/app_shell/test_q3dviewer_integration.py`

**Interfaces:**
- Consumes: `cancel_check: Callable[[], bool] | None`
- Produces: `load_gs_ply(path, T=None, cancel_check=None, chunk_rows=65536)` and `load_gaussian_ply(path, project_root, cancel_check=None)`

- [ ] **Step 1: Write the failing tests**

Add a generated binary PLY fixture with more rows than `chunk_rows`. Supply a callback that becomes true after the first conversion chunk and assert `InterruptedError`. Add an adapter test that monkeypatches `load_gs_ply`, records the callback, and proves cancellation is forwarded.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  .venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_q3dviewer_integration.py -k cancellation
```

Expected: failure because `load_gs_ply` and `load_gaussian_ply` do not accept `cancel_check`.

- [ ] **Step 3: Implement bounded conversion**

Change the fast loader to retain the header offset, create a read-only `np.memmap`, allocate the output record array once, and fill `pw`, `rot`, `scale`, `alpha`, and `sh` slices in `chunk_rows` ranges. Call a shared `_check_cancel(cancel_check)` before each range. Check before and after the meshio fallback.

In the adapter, forward `cancel_check` and validate `np.isfinite` in 65,536-row slices with cancellation checks.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run the Task 1 test command and the entire `test_q3dviewer_integration.py`.

---

### Task 2: Connect ViewerLoadWorker interruption to the parser

**Files:**
- Modify: `src/camera_system_app/workers/viewer_load_worker.py`
- Test: `tests/app_shell/test_q3dviewer_integration.py`

**Interfaces:**
- Consumes: Task 1 `load_gaussian_ply(..., cancel_check=None)`
- Produces: worker cancellation that emits neither `loaded` nor `failed`

- [ ] **Step 1: Write the failing worker test**

Monkeypatch `load_gaussian_ply` with a fake requiring `cancel_check`. Start a real `ViewerLoadWorker`, request interruption inside the fake, raise `InterruptedError`, wait for the worker, process Qt events, and assert neither signal was emitted.

- [ ] **Step 2: Run the test to verify RED**

Expected: failure because the worker does not pass `cancel_check` and reports the interruption through `failed`.

- [ ] **Step 3: Implement the worker boundary**

Pass `self.isInterruptionRequested` to the adapter. Catch `InterruptedError` separately and return silently. Keep ordinary parse failures on the existing `failed` signal.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run `tests/app_shell/test_q3dviewer_integration.py`.

---

### Task 3: Cancellable task packaging

**Files:**
- Modify: `Tx_Rx/tx_rx/jetson_client/task_manifest.py`
- Modify: `multiwebcam/src/multiwebcam/ui/coordinator.py`
- Test: `Tx_Rx/tests/test_task_manifest.py`
- Test: `multiwebcam/tests/ui/test_transfer_cancellation.py`

**Interfaces:**
- Produces: `build_configured_task_package(..., cancel_check=None)`, `build_task_package(..., cancel_check=None)`, and cancellation-aware hashing/copying

- [ ] **Step 1: Write failing package tests**

Create a capture fixture and a callback that cancels during the first file copy/hash. Assert `TaskPackageError("task packaging cancelled")`, no final staging directory, and no temporary staging directory.

Add a `_TaskPackageWorker` test whose fake builder requires and observes `cancel_check`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=Tx_Rx .venv-jetson/bin/python -m pytest -q Tx_Rx/tests/test_task_manifest.py -k cancel
PYTHONPATH=multiwebcam/src:Tx_Rx QT_QPA_PLATFORM=offscreen \
  LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  .venv-jetson/bin/python -m pytest -q -c pyproject.toml \
  multiwebcam/tests/ui/test_transfer_cancellation.py
```

- [ ] **Step 3: Implement cancellation propagation**

Add `CancelCheck`, `_check_cancel`, chunked `_copy_capture_file`, and cancellation-aware `_sha256_file`. Thread the callback through manifest description, package validation, and task checksum inputs without changing manifest bytes. The Qt worker passes `isInterruptionRequested` and suppresses cancellation failure signals during shutdown.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run both Task 3 commands.

---

### Task 4: Cancellable V4L2 discovery and safe camera-switch boundaries

**Files:**
- Modify: `multiwebcam/src/multiwebcam/sources/discovery.py`
- Modify: `multiwebcam/src/multiwebcam/sources/device.py`
- Modify: `multiwebcam/src/multiwebcam/ui/coordinator.py`
- Test: `multiwebcam/tests/sources/test_discovery.py`
- Test: `multiwebcam/tests/pipeline/test_session_startup.py`
- Test: `multiwebcam/tests/ui/test_transfer_cancellation.py`

**Interfaces:**
- Produces: `discover_frame_sources(cancel_check=None)`, cancellation-aware device option queries, and `FrameSource.start(cancel_check=None)`

- [ ] **Step 1: Write failing subprocess tests**

Use a fake `Popen` whose `poll()` remains pending. Flip cancellation after one poll and assert `terminate()`, `communicate()`, and no `kill()` when graceful termination succeeds. Add a timeout case that asserts terminate then kill when necessary.

Add worker tests proving `_DiscoveryWorker` and `_CameraSwitchWorker` forward their interruption callbacks and suppress cancellation during shutdown.

- [ ] **Step 2: Run tests to verify RED**

Run the discovery, session startup, and worker test modules.

- [ ] **Step 3: Implement owned subprocess polling**

Replace direct `subprocess.run` calls with `_run_command(args, timeout, cancel_check)`. Poll at no more than 50 ms, terminate on cancellation/timeout, allow a 250 ms reap window, kill if still running, and always call `communicate()`.

Check cancellation between `/dev/video*` devices, before/after source state transitions, and between warm-up reads. Do not force-kill an in-process OpenCV call.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run all Task 4 modules.

---

### Task 5: Bounded metadata and ACK cancellation

**Files:**
- Modify: `Tx_Rx/tx_rx/jetson_client/transfer.py`
- Modify: `multiwebcam/src/multiwebcam/ui/coordinator.py`
- Modify: `src/camera_system_app/application/reconstruction_service.py`
- Create: `Tx_Rx/tests/test_transfer_cancellation.py`
- Test: `Tx_Rx/tests/test_http_protocol.py`

**Interfaces:**
- Produces: `get_ply_metadata(..., cancel_check=None)` and `acknowledge_result(..., cancel_check=None)`
- ACK header: `Idempotency-Key: <task_id>`

- [ ] **Step 1: Write failing timeout/cancellation tests**

Use a fake session that raises `requests.Timeout` and flips cancellation after the first call. Assert a second attempt is not made after cancellation. Assert every attempt's connect/read timeout is no greater than the observation cap and the ACK carries the idempotency key.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=Tx_Rx .venv-jetson/bin/python -m pytest -q \
  Tx_Rx/tests/test_transfer_cancellation.py Tx_Rx/tests/test_http_protocol.py -k 'metadata or ack or cancel'
```

- [ ] **Step 3: Implement one-deadline timeout retries**

Add a private request helper that checks cancellation, computes the remaining overall deadline, performs one request with a one-second read cap, retries only `requests.Timeout`, and raises the existing `TransferError` when the deadline expires. Pass callbacks from both application workflows.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run both transfer test modules without `-k`.

---

### Task 6: JetPack-aware project dependency diagnostics

**Files:**
- Modify: `src/camera_system_app/application/diagnostics.py`
- Modify: `requirements/jetson.txt`
- Create: `docs/development/JETSON_DEPENDENCIES.md`
- Create: `tests/app_shell/test_diagnostics.py`

**Interfaces:**
- Produces: a `Python 项目依赖` diagnostic check

- [ ] **Step 1: Write failing diagnostic tests**

Monkeypatch module discovery to prove missing required project modules fail, missing qfluentwidgets only warns, and missing ONNX does not fail the runtime path.

- [ ] **Step 2: Run tests to verify RED**

Run `tests/app_shell/test_diagnostics.py`.

- [ ] **Step 3: Implement and document the dependency boundary**

Check required imports used by the Jetson runtime and optional imports separately. Document why generic `pip check` sees inherited Ubuntu/NVIDIA metadata, how to validate the core runtime, and when ONNX conversion dependencies are required. Do not install or upgrade Qt/ONNX packages.

- [ ] **Step 4: Run focused tests and diagnostics to verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_diagnostics.py
./scripts/jetson/diagnose.sh
```

---

### Task 7: Organize commits and run final gates

**Files:**
- Review: every modified and untracked source/test/doc file

**Interfaces:**
- Produces: coherent Git commits with no generated/runtime artifacts

- [ ] **Step 1: Audit ownership**

Use `git diff --name-only`, `git diff --stat`, and focused diffs to assign each file to q3dviewer, Tx_Rx, multiwebcam, or application-shell ownership. Confirm no capture/result/model file is staged.

- [ ] **Step 2: Run independent full suites**

```bash
QT_QPA_PLATFORM=offscreen LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  .venv-jetson/bin/python -m pytest -q

cd Tx_Rx && PYTHONPATH=. ../.venv-jetson/bin/python -m pytest -q

cd multiwebcam && PYTHONPATH=src:../Tx_Rx QT_QPA_PLATFORM=offscreen \
  LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  ../.venv-jetson/bin/python -m pytest -q
```

- [ ] **Step 3: Run static and Jetson gates**

```bash
.venv-jetson/bin/python -m compileall -q Tx_Rx/tx_rx multiwebcam/src/multiwebcam src/camera_system_app
git diff --check
./scripts/jetson/diagnose.sh
```

Run the opt-in X11 hardware test only when the active environment has a usable X11 display and NVIDIA OpenGL context.

- [ ] **Step 4: Commit coherent groups**

Stage explicit file lists, inspect `git diff --cached --stat` and
`git diff --cached --check`, then commit q3dviewer, Tx_Rx, multiwebcam, and
application-shell groups separately. Do not use broad recursive staging.
