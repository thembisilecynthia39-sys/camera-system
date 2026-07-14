"""Validate the local Jetson multimedia and inference stack for multiwebcam."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from multiwebcam.profiles import ProfileRepository
from multiwebcam.recognition.service_runtime import build_service_env


def _subprocess_env() -> dict[str, str]:
    return build_service_env()


def _run(command: list[str], *, env: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        return False, "missing executable"
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def _extract_last_json_line(output: str) -> dict | None:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _check_opencv() -> tuple[bool, list[str]]:
    try:
        import cv2
    except Exception as exc:
        return False, [f"OpenCV import failed: {exc}"]

    info = cv2.getBuildInformation()
    lines = [
        f"cv2={cv2.__version__}",
        f"cv2_path={cv2.__file__}",
        f"gstreamer={'GStreamer:                   YES' in info}",
        f"cuda={'NVIDIA CUDA:                   YES' in info or 'CUDA' in info}",
        f"PYTHONPATH={os.environ.get('PYTHONPATH', '')}",
    ]
    ok = "GStreamer:                   YES" in info
    return ok, lines


def _check_system_opencv() -> tuple[bool, list[str]]:
    command = [
        "env",
        "-u",
        "PYTHONPATH",
        "/usr/bin/python3",
        "-c",
        (
            "import cv2, json; "
            "info=cv2.getBuildInformation(); "
            "print(json.dumps({"
            "'version': cv2.__version__, "
            "'path': cv2.__file__, "
            "'gstreamer': 'GStreamer:                   YES' in info, "
            "'cuda': 'NVIDIA CUDA:                   YES' in info or 'CUDA' in info"
            "}))"
        ),
    ]
    ok, output = _run(command, env=_subprocess_env())
    if not ok:
        return False, [f"system OpenCV check failed: {output or 'no output'}"]
    payload = _extract_last_json_line(output)
    if payload is None:
        return False, [f"system OpenCV check returned unexpected output: {output}"]
    lines = [
        f"cv2={payload['version']}",
        f"cv2_path={payload['path']}",
        f"gstreamer={payload['gstreamer']}",
        f"cuda={payload['cuda']}",
        "invocation=env -u PYTHONPATH /usr/bin/python3",
    ]
    return bool(payload["gstreamer"]), lines


def _check_gstreamer_plugins() -> tuple[bool, list[str]]:
    plugins = ["nvv4l2decoder", "nvv4l2h264enc", "nvvidconv"]
    lines: list[str] = []
    ok = True
    for plugin in plugins:
        found, output = _run(["gst-inspect-1.0", plugin])
        ok = ok and found
        first_line = (output.splitlines() or ["no output"])[0]
        summary = "OK" if found else f"MISSING ({first_line})"
        lines.append(f"{plugin}: {summary}")
    return ok, lines


def _check_engine(engine_path: str | None, backend: str = "ultralytics_tensorrt") -> tuple[bool, list[str]]:
    if backend == "subprocess":
        return True, ["engine: checked via subprocess service"]
    if not engine_path:
        return True, ["engine: skipped (no path configured)"]
    engine = Path(engine_path)
    if not engine.exists():
        return False, [f"engine missing: {engine}"]
    try:
        from ultralytics import YOLO
    except Exception as exc:
        return False, [f"ultralytics import failed: {exc}"]
    try:
        YOLO(str(engine), task="detect")
    except Exception as exc:
        return False, [f"engine load failed: {exc}"]
    return True, [f"engine load OK: {engine}"]


def _check_subprocess_inference(settings) -> tuple[bool, list[str]]:
    if settings.inference.backend != "subprocess":
        return True, ["subprocess inference: skipped (backend is not subprocess)"]
    if not settings.inference.service_python and not settings.inference.service_conda_env:
        return False, ["subprocess inference: service_python/service_conda_env missing"]

    command = _service_python_command(
        settings,
        [
            "-c",
            (
                "import json, torch; "
                "payload = {"
                "'torch': torch.__version__, "
                "'cuda_available': torch.cuda.is_available(), "
                "'device_count': torch.cuda.device_count()"
                "}; "
                "print(json.dumps(payload))"
            ),
        ],
    )
    ok, output = _run(command, env=_subprocess_env())
    if not ok:
        return False, [f"service python check failed: {output or 'no output'}"]

    lines = [
        f"service_python={settings.inference.service_python}",
        f"service_conda_env={settings.inference.service_conda_env}",
    ]
    payload = _extract_last_json_line(output)
    if payload is None:
        return False, lines + [f"unexpected service output: {output}"]

    lines.extend(
        [
            f"torch={payload['torch']}",
            f"cuda_available={payload['cuda_available']}",
            f"device_count={payload['device_count']}",
        ]
    )
    ok = bool(payload["cuda_available"]) and int(payload["device_count"]) >= 1

    if settings.inference.engine_path:
        engine_ok, engine_lines = _check_service_engine(settings, settings.inference.engine_path)
        lines.extend(engine_lines)
        ok = ok and engine_ok

    return ok, lines


def _service_python_command(settings, extra_args: list[str]) -> list[str]:
    if settings.inference.service_python:
        return [
            settings.inference.service_python,
            *extra_args,
        ]
    if settings.inference.service_conda_env:
        return [
            "conda",
            "run",
            "-p",
            settings.inference.service_conda_env,
            "python",
            *extra_args,
        ]
    raise RuntimeError("subprocess inference requires service_python or service_conda_env")


def _check_service_engine(settings, engine_path: str) -> tuple[bool, list[str]]:
    engine = Path(engine_path)
    if not engine.exists():
        return False, [f"engine missing: {engine}"]
    command = _service_python_command(
        settings,
        [
            "-c",
            (
                "from ultralytics import YOLO; "
                f"YOLO({engine_path!r}, task='detect'); "
                "print('engine load OK')"
            ),
        ],
    )
    ok, output = _run(command, env=_subprocess_env())
    if not ok:
        return False, [f"engine load failed in service env: {output or 'no output'}"]
    return True, [f"engine load OK in service env: {engine}"]


def _check_jetson_release() -> tuple[bool, list[str]]:
    release_path = Path("/etc/nv_tegra_release")
    if not release_path.exists():
        return False, ["missing /etc/nv_tegra_release"]
    return True, [release_path.read_text().strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()

    repo = ProfileRepository(args.project)
    settings = repo.load_settings()

    checks = [
        ("jetson_release", _check_jetson_release),
        ("opencv", _check_opencv),
        ("system_opencv", _check_system_opencv),
        ("gstreamer_plugins", _check_gstreamer_plugins),
        ("subprocess_inference", lambda: _check_subprocess_inference(settings)),
        ("tensorrt_engine", lambda: _check_engine(settings.inference.engine_path, settings.inference.backend)),
    ]

    failures = 0
    for name, fn in checks:
        ok, lines = fn()
        print(f"[{name}] {'OK' if ok else 'FAIL'}")
        for line in lines:
            print(f"  {line}")
        if not ok:
            failures += 1

    active_profiles = [profile for profile in repo.load_all() if not profile.ignore]
    print(f"[profiles] active={len(active_profiles)}")
    for profile in active_profiles:
        print(
            "  "
            f"source_id={profile.source_id} "
            f"backend={profile.capture_backend} "
            f"resolution={profile.resolution[0]}x{profile.resolution[1]} "
            f"fps={profile.capture_fps} "
            f"pixel_format={profile.pixel_format}"
        )

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
