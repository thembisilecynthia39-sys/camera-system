# Cancellation and Dependency Hygiene Design

## Context

The first reliability pass fixed upload cancellation, recording rollback, and
shared shutdown deadlines. Five residual risks remain:

1. The application-shell Gaussian loader checks `QThread` interruption only
   before and after a complete PLY parse.
2. Camera discovery, camera switching, and task packaging contain blocking
   work that does not consistently receive the owning worker's interruption
   state.
3. Metadata and result ACK calls can remain inside a `requests` call for the
   full configured request timeout.
4. The working tree contains several related but uncommitted reliability and
   Jetson rendering changes.
5. Generic `pip check` reports packages inherited from JetPack's system Python
   as if they were application dependencies.

Jetson Orin Nano with JetPack 5.1.1 remains the production acceptance target.
The project must keep using the system OpenCV, PyQt5-backed PySide6 shim,
CUDA, TensorRT, and related JetPack libraries.

## Considered Approaches

### Recommended: cooperative cancellation with bounded external operations

Thread interruption is propagated as a callable through file parsing,
packaging, discovery, and transfer APIs. CPU and file operations process data
in bounded chunks. External subprocesses and HTTP calls use short observation
windows inside one overall deadline.

This keeps the current architecture and data ownership, works on Python 3.8,
and adds deterministic tests without introducing new runtime services.

### Process isolation for every long operation

PLY parsing, camera discovery, task packaging, and HTTP transfer could each run
in a child process that is terminated on shutdown. This offers hard
termination, but transferring large NumPy arrays between processes increases
memory pressure and camera objects cannot safely cross the process boundary.
It is unsuitable for the Orin Nano memory budget.

### Timeout-only mitigation

Existing calls could retain their implementation and use smaller fixed
timeouts. This is simple, but large local PLY and task-package operations have
no timeout boundary, and globally shortening network timeouts would create
false failures on slow but healthy links.

## Design

### Cancellable Gaussian loading

`q3dviewer.utils.cloud_io.load_gs_ply` accepts an optional cancellation
callback. The binary fast path memory-maps the vertex payload and converts it
to the renderer record type in bounded row chunks. Cancellation is checked:

- while parsing the header;
- before mapping the payload;
- between conversion chunks;
- before and after the compatibility fallback loader.

The application adapter forwards the callback and validates finite values in
chunks. `ViewerLoadWorker` supplies `isInterruptionRequested`. Cancellation
does not emit a user-visible parse failure.

### Cancellable discovery, switching, and packaging

V4L2 queries use a small internal command runner based on `subprocess.Popen`.
It polls at short intervals, terminates the child when cancellation is
requested, kills it only if graceful termination misses a bounded cleanup
window, and preserves the existing 5/10-second total timeouts.

Task-package APIs accept a cancellation callback. File copying and SHA-256
calculation are chunked and check cancellation between chunks. Temporary
staging directories continue to be removed atomically on cancellation.

Camera switching checks interruption at each safe state boundary and passes it
through camera warm-up. OpenCV device opening itself cannot be asynchronously
terminated without corrupting the in-process capture object, so it remains
bounded by the backend/startup timeout and is documented as best-effort.

### Metadata and ACK network cancellation

Metadata GET and result ACK accept a cancellation callback. Each request uses
a short connect/read observation window inside the configured overall
deadline. Timeouts are retried only while the overall deadline remains.
Cancellation is checked between attempts.

ACK requests include `Idempotency-Key: <task_id>` so retrying after an
ambiguous timeout does not create a second logical acknowledgement. Protocol
and integration tests verify the header and cancellation latency boundary.

### Dependency hygiene

The project does not upgrade or replace JetPack's Qt, OpenCV, CUDA, TensorRT,
`launchpadlib`, or `onnx-graphsurgeon` packages. Generic `pip check` is not an
acceptance gate for this system-site-packages virtual environment because it
evaluates unrelated Ubuntu/NVIDIA distributions.

The application diagnostic report gains a project dependency check that:

- imports every runtime dependency actually used by the selected Jetson path;
- reports the PySide6 compatibility shim and underlying Qt version;
- classifies qfluentwidgets as optional and confirms fallback widgets remain
  available;
- explains that ONNX tooling is optional unless model conversion is requested.

The Jetson requirements documentation records these boundaries and provides
separate commands for core runtime and optional model-conversion checks.

### Commit organization

After all tests pass, the dirty tree is committed by coherent ownership:

1. q3dviewer rendering and cancellable PLY loading;
2. Tx_Rx transfer cancellation;
3. multiwebcam capture, recording, inference, and worker shutdown;
4. application-shell integration and diagnostics;
5. tests and documentation paired with their owning change where practical.

No generated files, virtual environments, runtime logs, captures, or result
models are committed. Each staged group receives `git diff --cached --check`
and focused tests before commit.

## Error Handling

All cooperative cancellation paths raise subsystem-specific cancellation
errors internally and suppress them at worker boundaries. Partial staging
directories and partial downloads remain recoverable or are removed according
to their existing atomic-publication rules. Subprocess termination is always
followed by `communicate()` to reap the child.

Network protocol validation remains unchanged after a successful response.
Only timeout retries are automatic; validation failures and non-timeout HTTP
errors fail immediately.

## Verification

- Unit tests prove each cancellation callback is observed inside the relevant
  operation, not merely before or after it.
- Subprocess tests prove terminate/reap behavior and timeout behavior.
- HTTP tests prove bounded timeout retries, cancellation, identity validation,
  and ACK idempotency headers.
- Dependency diagnostic tests run without importing optional model-conversion
  packages.
- Root, Tx_Rx, and multiwebcam test suites pass independently.
- `compileall`, `git diff --check`, Jetson diagnostics, and the opt-in X11
  OpenGL hardware test form the final gates.
