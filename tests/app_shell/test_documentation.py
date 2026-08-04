"""Repository documentation and dependency-layout checks."""

from pathlib import Path
import re


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


def test_root_readme_covers_operator_and_developer_workflows():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    required_text = (
        "## 支持平台",
        "## 快速开始",
        "./scripts/jetson/install.sh",
        "./scripts/jetson/diagnose.sh",
        "./scripts/jetson/run.sh",
        "## 配置",
        "## 取消、超时与安全退出",
        "## 开发与测试",
        "requirements/dev.txt",
        "## 常见问题",
    )

    for text in required_text:
        assert text in readme


def test_root_readme_relative_links_resolve():
    readme_path = PROJECT_ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", readme)

    for raw_target in targets:
        target = raw_target.strip().strip("<>").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        assert (readme_path.parent / target).resolve().exists(), raw_target
