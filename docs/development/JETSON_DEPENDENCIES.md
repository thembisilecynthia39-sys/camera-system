# Jetson Dependency Policy

The production runtime is Jetson Orin Nano with JetPack 5.1.1. Its Python
environment intentionally inherits Ubuntu and NVIDIA system packages so the
application can use the verified Qt, OpenCV/GStreamer, CUDA, TensorRT, and
camera stack.

## Core runtime acceptance

Install only the project-owned pure Python packages:

```bash
.venv-jetson/bin/python -m pip install -r requirements/jetson.txt
```

Validate the application runtime:

```bash
./scripts/jetson/diagnose.sh
```

The diagnostic imports the modules used by capture, recording, transfer, and
the Gaussian viewer. A missing core module is a failure. Missing model
conversion or optional Fluent styling modules are reported as warnings.

## Why generic `pip check` reports unrelated packages

The virtual environment uses `--system-site-packages`. Consequently, `pip
check` evaluates every inherited Ubuntu and NVIDIA distribution, including
packages the Camera System never imports:

- Ubuntu's `launchpadlib` metadata references `testresources`.
- NVIDIA's `onnx-graphsurgeon` metadata references `onnx`.
- User-installed qfluentwidgets releases declare PyQt 5.15 or newer, while
  JetPack 5.1.1 supplies Qt/PyQt 5.12/5.14.

These messages must not be fixed by upgrading or replacing JetPack's PyQt5,
OpenCV, CUDA, or TensorRT packages. Such upgrades can break the native ABI and
the camera/OpenGL stack.

## Optional ONNX conversion

The running application uses the configured TensorRT `.engine` model and does
not import ONNX. ONNX and ONNX GraphSurgeon are required only when converting
or editing models. Perform conversion in a separate environment or container
whose ONNX version matches the installed TensorRT release; copy only the
resulting engine into the Jetson runtime.

## Optional Fluent widgets

The application provides `multiwebcam.ui.fluent` as a compatibility boundary.
When qfluentwidgets cannot load against JetPack's Qt version, the UI uses the
built-in Qt widgets and the project theme. qfluentwidgets is therefore not a
core Jetson dependency.
