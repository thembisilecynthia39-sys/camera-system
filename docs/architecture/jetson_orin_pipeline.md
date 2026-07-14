# Jetson Orin Nano Pipeline

This project now supports a Jetson-oriented path with:

- GStreamer camera capture via `cv2.CAP_GSTREAMER`
- Jetson hardware H.264 encoding via `nvv4l2h264enc`
- Asynchronous GPU recognition with a TensorRT `.engine` through Ultralytics

## When To Use This Path

Use this path when the target machine is a Jetson Orin Nano and the goal is to keep USB capture responsive while moving H.264 encoding and object recognition onto NVIDIA-accelerated components.

For non-Jetson desktop validation, keep `[recording].backend = "pyav"` and use the normal test command:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check .
```

## Prerequisites

- JetPack 6.x on Orin Nano
- OpenCV built with `GStreamer=ON`
- GStreamer plugins from JetPack (`nvv4l2decoder`, `nvv4l2h264enc`, `nvvidconv`)
- A TensorRT engine file if you want GPU recognition

Recommended OpenCV build flags:

```bash
-DWITH_GSTREAMER=ON
-DWITH_CUDA=ON
-DWITH_CUDNN=ON
-DOPENCV_DNN_CUDA=ON
-DCUDA_ARCH_BIN=8.7
```

## Configuration

Edit `multiwebcam.toml`:

```toml
[recording]
backend = "gstreamer"
codec = "h264"
fps = 30
jetson_encoder = "nvv4l2h264enc"
bitrate = 8000000
preset_level = 1
insert_sps_pps = true
maxperf_enable = true

[inference]
backend = "subprocess"
engine_path = "/home/lab/models/yolo11n.engine"
device = "cuda:0"
input_size = [640, 640]
confidence_threshold = 0.25
interval_ms = 100
target_class_ids = [0]
service_conda_env = "/home/lab/.conda/envs/multiwebcam-jetson-py38"
service_backend = "ultralytics_tensorrt"
service_script = "/home/lab/3DGS/Multcamera/multiwebcam/scripts/services/inference_service.py"

[[sources]]
source_id = 0
label = "front_left"
bus_info = "usb-3610000.xhci-2.4.2"
ignore = false
resolution = [1280, 720]
pixel_format = "mjpeg"
capture_fps = 30
capture_backend = "gstreamer"

[[sources]]
source_id = 1
label = "front_right"
bus_info = "usb-3610000.xhci-2.4.3"
ignore = false
resolution = [1280, 720]
pixel_format = "mjpeg"
capture_fps = 30
capture_backend = "gstreamer"

[[sources]]
source_id = 2
label = "top"
bus_info = "usb-3610000.xhci-2.2.2"
ignore = false
resolution = [640, 480]
pixel_format = "mjpeg"
capture_fps = 30
capture_backend = "gstreamer"
```

This mixed setup is supported directly: each source keeps its own configured capture resolution, while `input_size = [640, 640]` remains the TensorRT model input size for all cameras.

The subprocess inference mode is the current engineering path when your main `multiwebcam` environment is Python 3.10+ but NVIDIA's Jetson-optimized PyTorch and TensorRT runtime are only available in a separate Python 3.8 environment. The main app sends JPEG-compressed preview frames to `service_conda_env`, and the worker returns bounding boxes over stdio.

`capture_backend = "gstreamer"` tells `FrameSource` to build a Jetson-friendly pipeline automatically for MJPEG or YUYV USB cameras. If you need a fully custom pipeline, add:

```toml
gstreamer_pipeline = "v4l2src device=/dev/video0 ... ! appsink drop=true max-buffers=1 sync=false"
```

## Recognition Backend

The TensorRT path uses Ultralytics to execute a prebuilt `.engine` file. Export example:

```bash
yolo export model=yolo11n.pt format=engine device=0 half=True imgsz=640
```

Runtime behavior:

- capture threads stay on the camera path
- recognition runs in a background worker
- only the newest frame per camera is kept for inference
- stale frames are dropped instead of blocking capture

That is the key behavior needed on Orin Nano: GPU inference should never back-pressure USB capture.

## Recording Backend

With `[recording].backend = "gstreamer"`, `FrameRecorder` writes frames through:

```text
appsrc -> videoconvert -> nvvidconv -> nvv4l2h264enc -> h264parse -> qtmux -> filesink
```

This moves H.264 encoding off CPU and onto the Jetson hardware encoder.

## Validation

Smoke tests run in the repo with:

```bash
QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check .
```

The automated tests validate:

- profile/settings round-trip
- Jetson capture pipeline generation
- Jetson recording pipeline generation
- quality scoring with detector-provided object regions

On the Orin Nano itself, run the hardware checks:

```bash
python scripts/jetson/validate_jetson_stack.py --project /path/to/project
python scripts/jetson/jetson_smoke_pipeline.py --project /path/to/project --run-inference
```

The first script validates:

- Jetson release file present
- OpenCV import and build flags
- required GStreamer plugins
- TensorRT engine load through Ultralytics

The second script validates the end-to-end path:

- configured cameras deliver frames
- TensorRT recognition runs on the latest frame
- recording writes `cam_N.mp4` plus `timestamps.csv`

## Current Jetson Validation Snapshot

Validated on 2026-06-26 in the actual Jetson environment with non-sandboxed device access.

Passing:

- Jetson release is detected: `R35.3.1`.
- NVIDIA GStreamer plugins are available: `nvv4l2decoder`, `nvv4l2h264enc`, `nvvidconv`.
- Subprocess inference environment sees CUDA and loads `yolo11n.engine`.
- Four UVC capture devices are visible: `/dev/video0`, `/dev/video2`, `/dev/video4`, `/dev/video6`.
- Current active project profile captures three devices and completes smoke recording.

Smoke result:

```text
[capture] OK
/dev/video2: fps=30.2
/dev/video0: fps=29.9
/dev/video6: fps=15.2
[inference] backend=subprocess
[recording] cam_2=90 frames, cam_4=90 frames, cam_5=45 frames, timestamps=True
```

Known constraints in the current setup:

- The active profile uses `opencv_v4l2` capture and `pyav` recording, not the GStreamer hardware encoder path.
- The `.venv` OpenCV wheel reports `GStreamer: NO`.
- Clearing `PYTHONPATH` still imports `.venv` OpenCV `4.13.0`, which has no GStreamer.
- `/usr/bin/python3` imports system OpenCV `4.2.0` with GStreamer support.
- `/dev/video6` currently runs at about 15fps in the active three-camera configuration.
- Four-camera concurrent probes show USB bandwidth pressure, including no-frame and `No space left on device` failures.

A/B camera swap result:

- Replacing active `/dev/video6` (`usb-3610000.xhci-2.4.3`) with `/dev/video4` (`usb-3610000.xhci-2.4.2`) restores the expected profile.
- The swapped setup, still using two `1280x720@30` streams plus one `640x480@30` stream, records all active cameras at about 30fps.

```text
/dev/video4: fps=29.8, cam_1 frames=89
/dev/video2: fps=30.1, cam_2 frames=90
/dev/video0: fps=29.9, cam_4 frames=90
```

This points to `/dev/video6`, its camera, its cable, or the `usb-3610000.xhci-2.4.3` branch as the current bottleneck.

### Updated USB2 topology validation (2026-07-13)

After reconnecting the USB2 cameras, the topology was re-enumerated as:

```text
/dev/video0  usb-3610000.xhci-1.3       USB3, 1280x720
/dev/video2  usb-3610000.xhci-2.1.2     USB2, 640x480
/dev/video4  usb-3610000.xhci-2.4.3     USB2, 1280x720
/dev/video6  usb-3610000.xhci-2.4.4     USB2, 1280x720
```

The low-resolution stream must be assigned to the `2.1.2` USB2 branch for
this physical setup.  The alternative assignment (`video6=640x480` with
`video2` and `video4` at 720p) is rejected by V4L2 with `No space left on
device`, while the assignment above delivers all three USB2 streams.

With the fixed USB3 camera added, the project's `CaptureSession` was run for
five seconds with no startup errors:

```text
active=/dev/video0,/dev/video2,/dev/video4,/dev/video6
errors={}
healthy=True
```

The Qt event-loop smoke test also completed with the same four active paths;
camera warm-up runs in the background camera-load worker so the initial window
is not blocked by V4L2 startup.

Important note for automated validation: sandboxed command execution can hide `/dev/video*`, `/dev/nvmap`, and NVIDIA device nodes. Hardware validation must run with direct device access.

## Troubleshooting Checklist

- If OpenCV cannot open the GStreamer source, confirm the OpenCV build includes `GStreamer=ON`.
- If encoding fails, confirm `nvv4l2h264enc`, `nvvidconv`, `h264parse`, and `qtmux` are available through `gst-inspect-1.0`.
- If subprocess inference fails immediately, confirm `service_python` or `service_conda_env` points to the Python environment that can import `ultralytics`, CUDA PyTorch, and TensorRT dependencies.
- If capture stutters while inference runs, confirm the app is using the async/subprocess inference path and that only the newest frame per source is being processed.
- If camera discovery is unstable, run `scripts/diagnostics/diagnose_usb_cameras.py` and compare `bus_info` values against `multiwebcam.toml`.
- If `/dev/video*` is visible in `/sys/class/video4linux` but missing under `/dev`, check whether the command is running in a sandbox or restricted device namespace.
- If one camera runs at half rate, test USB topology changes and reduce one or more high-resolution streams before blaming application logic.
