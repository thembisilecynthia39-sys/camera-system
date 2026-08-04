# README and Requirements Completion Design

## Goal

Make the repository usable from the root directory without requiring a reader
to infer installation commands or combine dependency declarations from the
three component projects. Keep Jetson Orin Nano with JetPack 5.1.1 as the
production baseline.

## Documentation structure

The root `README.md` becomes the primary quick-start document. It will cover:

- supported hardware and software;
- repository capabilities and module boundaries;
- Jetson installation, configuration, diagnosis, and launch;
- the capture-to-viewer workflow;
- cancellation and timeout behavior;
- development and test commands;
- runtime directories, troubleshooting, and links to detailed documents.

Component READMEs remain authoritative for standalone component usage. The root
README links to them instead of duplicating their complete APIs.

## Dependency structure

Dependency files have distinct responsibilities:

- `requirements/jetson.txt`: exact, verified production runtime versions;
- `requirements.txt`: conventional root entry point that includes the Jetson
  runtime lock;
- `requirements/dev.txt`: runtime lock plus Python 3.8-compatible test tools;
- `requirements/README.md`: explains which file to use and which packages must
  continue to come from JetPack or Ubuntu.

The installer continues to consume `requirements/jetson.txt` directly so the
production source of truth remains explicit.

## Platform constraints

Do not install PySide6, PyQt5, pip OpenCV, CUDA, TensorRT, Torch, or ONNX into
the production requirements. Qt, OpenCV/GStreamer, CUDA, TensorRT, and Torch
must use the JetPack-compatible system builds. ONNX remains an optional,
separate model-conversion environment.

The development file contains only tools needed by repository checks and must
remain compatible with Python 3.8.

## Verification

Verify:

1. requirement include paths resolve from both the repository root and the
   Jetson installer;
2. all documented local links and commands reference existing files;
3. the dependency diagnostic reports no core failures;
4. the root tests and release packaging tests pass;
5. `git diff --check` reports no formatting errors.

