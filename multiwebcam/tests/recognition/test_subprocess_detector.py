from __future__ import annotations

import os
import site
import subprocess
import sys
import textwrap

import numpy as np

from multiwebcam.profiles.settings import InferenceSettings
from multiwebcam.recognition import create_detector
from multiwebcam.recognition.subprocess_detector import SubprocessObjectDetector, _sanitized_service_env


def test_subprocess_detector_roundtrip(tmp_path):
    script_path = tmp_path / "fake_detector.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            sys.stdout.write(json.dumps({"status": "ready", "backend": "fake"}) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                payload = json.loads(line)
                if payload.get("command") == "shutdown":
                    break
                sys.stdout.write(json.dumps({
                    "status": "ok",
                    "backend": "fake_subprocess",
                    "frame_index": payload["frame_index"],
                    "latency_ms": 4.2,
                    "object_region": {
                        "x": 1,
                        "y": 2,
                        "width": 30,
                        "height": 40,
                        "area_ratio": 0.12,
                        "centeredness": 0.7,
                        "fill_ratio": 1.0,
                        "confidence": 0.95
                    }
                }) + "\\n")
                sys.stdout.flush()
            """
        ),
        encoding="utf-8",
    )
    settings = InferenceSettings(
        backend="subprocess",
        service_python=sys.executable,
        service_backend="heuristic",
        service_script=str(script_path),
    )
    detector = create_detector(settings)
    try:
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        result = detector.detect(frame, frame_index=12)
    finally:
        detector.close()

    assert result.frame_index == 12
    assert result.backend == "fake_subprocess"
    assert result.object_region is not None
    assert result.object_region.width == 30
    assert result.object_region.confidence == 0.95


def test_subprocess_detector_includes_remote_traceback(tmp_path):
    script_path = tmp_path / "fake_detector_error.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            sys.stdout.write(json.dumps({"status": "ready", "backend": "fake"}) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                payload = json.loads(line)
                if payload.get("command") == "shutdown":
                    break
                sys.stdout.write(json.dumps({
                    "status": "error",
                    "error": "remote boom",
                    "traceback": "Traceback\\\\n  remote stack"
                }) + "\\n")
                sys.stdout.flush()
            """
        ),
        encoding="utf-8",
    )
    settings = InferenceSettings(
        backend="subprocess",
        service_python=sys.executable,
        service_backend="heuristic",
        service_script=str(script_path),
    )
    detector = create_detector(settings)
    try:
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        try:
            detector.detect(frame, frame_index=1)
            assert False, "expected detect() to raise"
        except RuntimeError as exc:
            assert "remote boom" in str(exc)
            assert "remote stack" in str(exc)
    finally:
        detector.close()


def test_subprocess_detector_skips_non_json_stdout_noise(tmp_path):
    script_path = tmp_path / "fake_detector_stdout_noise.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            sys.stdout.write("Ultralytics banner line\\n")
            sys.stdout.write(json.dumps({"status": "ready", "backend": "fake"}) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                payload = json.loads(line)
                if payload.get("command") == "shutdown":
                    break
                sys.stdout.write("[TRT] noisy stdout log\\n")
                sys.stdout.write(json.dumps({
                    "status": "ok",
                    "backend": "fake_subprocess",
                    "frame_index": payload["frame_index"],
                    "latency_ms": 1.5,
                    "object_region": None
                }) + "\\n")
                sys.stdout.flush()
            """
        ),
        encoding="utf-8",
    )
    settings = InferenceSettings(
        backend="subprocess",
        service_python=sys.executable,
        service_backend="heuristic",
        service_script=str(script_path),
    )
    detector = create_detector(settings)
    try:
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        result = detector.detect(frame, frame_index=3)
    finally:
        detector.close()

    assert result.frame_index == 3
    assert result.backend == "fake_subprocess"
    assert result.object_region is None


def test_sanitized_service_env_drops_python_overrides(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/tmp/poison")
    monkeypatch.setenv("PYTHONHOME", "/tmp/home")
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/venv")
    monkeypatch.setenv("CONDA_PREFIX", "/tmp/conda")

    env = _sanitized_service_env()

    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert "VIRTUAL_ENV" not in env
    assert "CONDA_PREFIX" not in env
    assert "PYTHONNOUSERSITE" not in env
    assert env["PATH"] == os.environ["PATH"]


def test_sanitized_service_env_preserves_user_site_packages(monkeypatch):
    script = "import json, site; print(json.dumps(site.ENABLE_USER_SITE))"
    env = _sanitized_service_env()
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert site.getusersitepackages()
    assert result.stdout.strip() == "true"


def test_service_python_is_preferred_over_conda_run():
    settings = InferenceSettings(
        backend="subprocess",
        service_python="/opt/jetson/bin/python",
        service_conda_env="/opt/jetson-env",
        service_backend="heuristic",
    )
    detector = SubprocessObjectDetector.__new__(SubprocessObjectDetector)
    detector._settings = settings
    detector._service_backend = "heuristic"

    command = detector._base_command("/tmp/inference_service.py")

    assert command[0] == "/opt/jetson/bin/python"
    assert "conda" not in command
