"""Repository documentation and dependency-layout checks."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _requirement_entries(path: Path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_requirement_entry_points_are_layered():
    runtime = _requirement_entries(PROJECT_ROOT / "requirements.txt")
    development = _requirement_entries(
        PROJECT_ROOT / "requirements" / "dev.txt"
    )

    assert runtime == ["-r requirements/jetson.txt"]
    assert development[0] == "-r jetson.txt"
    assert "pytest>=7,<9" in development


def test_jetson_requirements_do_not_replace_platform_packages():
    entries = [
        entry.lower()
        for entry in _requirement_entries(
            PROJECT_ROOT / "requirements" / "jetson.txt"
        )
    ]
    prohibited = (
        "pyside6",
        "pyqt5",
        "opencv-python",
        "opencv-contrib-python",
        "torch",
        "onnx",
        "tensorrt",
        "cuda",
    )

    for package in prohibited:
        assert not any(
            entry == package
            or entry.startswith(package + "==")
            or entry.startswith(package + ">")
            or entry.startswith(package + "<")
            for entry in entries
        )
