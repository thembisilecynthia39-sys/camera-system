# Tx_Rx

Jetson-to-WSL reconstruction task protocol client and staging package builder.

The current package builds and validates an eight-image task, uploads it to
the WSL receiver, starts reconstruction, polls task status, downloads the PLY
with validated HTTP ranges, and sends a result ACK. It does not contain the
WSL HTTP server, the GaussianObject reconstruction process, Qt integration, or
the multi-camera capture entry point.

## Current status

- The pure Python transfer path is implemented and covered by a local
  simulated HTTP receiver.
- The test suite covers upload/reconstruct responses, status polling, PLY
  metadata, Range downloads, hashes, cancellation, atomic publication and
  ACK handling.
- A real cross-device Jetson-to-WSL run, a large real GaussianObject PLY and
  Qt/multiwebcam integration are still not verified.

The implementation and verification snapshot is recorded in
[`markdown/TX纯Python_HTTP客户端实现报告.md`](markdown/TX纯Python_HTTP客户端实现报告.md).

## Install

```bash
python3 -m pip install -e .
```

## Build a task package

```python
from pathlib import Path

from tx_rx.jetson_client import build_configured_task_package

result = build_configured_task_package(Path("captures/capture_001"))
print(result.manifest_path)
```

The visible task directory is controlled only by `staging_root` in
`config.yaml`. The supplied configuration uses:

```text
/home/jetson/3DGS/camera_system/Tx_Rx/staging
```

The transfer client consumes the completed directory returned in
`result.staging_dir`; it does not upload directly from the capture directory.
Before upload, it calls `load_staged_task_package(result.staging_dir)` so the
manifest, all hashes, and the task checksum are validated again.

## Manual eight-image tasks

Create a named directory under the configured staging root and put exactly
eight non-empty JPEG files in its `images` directory:

```text
staging/manual_001/images/0.jpg
staging/manual_001/images/1.jpg
...
staging/manual_001/images/7.jpg
```

`scan_staging_tasks()` detects the directory and calls
`prepare_manual_task()` to add `metadata.json` and `task.json` in place. This
package does not include a desktop UI; an external application may use the
scan helper for display, but the provided transfer path is the explicit CLI
workflow below.

Set the WSL receiver address in `config.yaml`:

```yaml
server_url: http://10.150.14.62:8000
```

The uploader calls `GET /health`, uploads a ZIP with `POST /upload`, then calls
`POST /reconstruct` with the returned task ID. It never reads an original
capture directory.

Users may select any eight `.jpg` or `.jpeg` files from a larger image pool.
The pool may be `capture_dir/images/` or the capture directory itself. Pass each
filename with `--image` in the intended index order; no angle records are
required in `metadata.csv`. The eight arguments map to indexes 0 through 7 and
the protocol angles `0, 45, 90, 135, 180, 225, 270, 315`. Without explicit
selection, an exactly-eight directory is sorted by filename, while existing
multi-round metadata selection remains available for compatibility.

## Test

```bash
python3 -m compileall -q .
pytest -q
```

## Pure Python transfer workflow

Set `server_url` in `config.yaml` to the actual WSL IP address, then run:

```bash
python3 -m tx_rx.jetson_client.transfer \
  --capture-dir /path/to/completed/capture \
  --config config.yaml \
  --image selected-a.jpg \
  --image selected-b.jpg \
  --image selected-c.jpg \
  --image selected-d.jpg \
  --image selected-e.jpg \
  --image selected-f.jpg \
  --image selected-g.jpg \
  --image selected-h.jpg
```

The command builds and uploads the ZIP, starts reconstruction, polls status,
downloads the PLY with validated HTTP ranges, atomically publishes
`3DGS.ply`, and sends the result ACK. It does not use Qt or run network work
on a UI thread.

## Documentation classification

### User documentation

This README is the user-facing entry point for installation, task preparation
and the pure Python transfer command.

### Implementation and verification

- [`markdown/TX纯Python_HTTP客户端实现报告.md`](markdown/TX纯Python_HTTP客户端实现报告.md)：current implementation and test snapshot.

### Protocol and historical records

- [`TX审查.md`](TX审查.md)：historical Jetson-side compatibility review.
- [`RX审查.md`](RX审查.md)：WSL receiver protocol and integration review.
- [`提示词.md`](提示词.md)：development requirements and test checklist, not a user guide.

The review documents preserve conclusions from their respective review points;
they are not the source of truth for the current client implementation.
