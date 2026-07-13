NOTE: This project is currently in substantial flux as I basically do a complete re-write using PyAV rather than OpenCV. It's more of a personal project at this time as I work through polishing it up. I may not have time to dedicate to making meaningful progress on it until April of 2026. Caveat emptor.

# multiwebcam

Multi-camera capture and recording for USB webcams on Linux. Output feeds into [Caliscope](https://github.com/mprib/caliscope) for calibration and 3D reconstruction.

## What This Does

Captures video from multiple USB webcams simultaneously, recording to individual MP4 files with accurate timestamps. Each camera gets:
- `cam_N.mp4` - H.264 encoded video
- `timestamps.csv` - Combined frame timestamps for temporal alignment (all cameras)

This is **not** hardware-synchronized capture. Consumer USB webcams have no genlock. We capture independently and record timestamps so Caliscope can align frames temporally (typical precision: 10-50ms).

## Requirements

- Linux with V4L2 support
- Python 3.11+
- v4l2-utils (`sudo apt install v4l-utils`)
- USB webcams

### Camera Compatibility

Simple, cheap, "dumb" USB webcams work best. Cameras that just stream frames without complex firmware (like the **eMeet C960**) are reliable and predictable.

Feature-rich cameras (autofocus, dynamic exposure modes, HDR) tend to be **less** reliable. Their firmware can hang when V4L2 controls are changed mid-stream, sometimes requiring a physical USB replug to recover. The **Razer Kiyo Pro**, for example, freezes when switching exposure modes during capture.

**Tested and recommended**: eMeet C960

**Known issues**: Razer Kiyo Pro (firmware hangs on exposure mode changes), Logitech C920/C930e (similar firmware instability)

## Installation

```bash
git clone https://github.com/mprib/multiwebcam
cd multiwebcam
uv sync
```

## Usage

Run from any directory you want to use as a project folder:

```bash
mwc
# or
multiwebcam
```

On first run, cameras are discovered and saved to `multiwebcam.toml`. On subsequent runs, the saved configuration is loaded.

### Jetson Orin Nano

The capture stack now supports a Jetson-oriented path:

- per-camera `capture_backend = "gstreamer"` for USB ingest through GStreamer
- `[recording].backend = "gstreamer"` for `nvv4l2h264enc` hardware encoding
- `[inference].backend = "ultralytics_tensorrt"` for asynchronous GPU recognition
- `[inference].device = "cuda:0"` to pin TensorRT execution to the expected CUDA device
- mixed source resolutions are supported per camera, for example `2x 1280x720` plus `1x 640x480`

When the main app runtime cannot use Jetson's Python 3.8-only TensorRT stack directly, the project also supports `[inference].backend = "subprocess"` with `service_conda_env` pointing at a dedicated py38 environment. In that mode the Qt app stays on Python 3.10+, while recognition runs in a separate worker process.

See [docs/jetson_orin_pipeline.md](/home/lab/3DGS/Multcamera/multiwebcam/docs/jetson_orin_pipeline.md) for the full Orin Nano configuration, required OpenCV build flags, and a sample `multiwebcam.toml`.
For device-side validation, use `scripts/validate_jetson_stack.py` and `scripts/jetson_smoke_pipeline.py`.

### Controls

- **Grid View**: Shows all cameras with live preview and stats
- **Focus**: Click to see single camera large
- **Back to Grid**: Return to multi-camera view
- **Record/Stop**: Start/stop recording to `recordings/` folder

### Output Structure

```
your_project/
├── multiwebcam.toml      # Camera configuration
└── recordings/
    ├── cam_0.mp4
    ├── cam_1.mp4
    ├── timestamps.csv     # Combined timestamps for all cameras
    └── ...
```

## Troubleshooting

**Camera not detected?**
```bash
v4l2-ctl --list-devices
```

**Dark/overexposed image?**
Check exposure mode:
```bash
v4l2-ctl -d /dev/video0 --get-ctrl=auto_exposure
v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=3  # Auto mode
```

**Permission denied?**
Add user to video group:
```bash
sudo usermod -aG video $USER
# Log out and back in
```

## License

BSD-2-Clause. See LICENSE file.

## Related

- [Caliscope](https://github.com/mprib/caliscope) - Multi-camera calibration and 3D reconstruction
