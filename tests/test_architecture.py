"""Static checks for the dependency boundaries documented in docs/."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Set


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _imports(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _python_files(*paths: Path) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            yield path
        else:
            yield from path.rglob("*.py")


def _assert_imports_exclude(paths: Iterable[Path], prefixes: Set[str]) -> None:
    violations = []
    for path in paths:
        for imported in sorted(_imports(path)):
            if any(
                imported == prefix or imported.startswith(prefix + ".")
                for prefix in prefixes
            ):
                violations.append(
                    "{} imports {}".format(path.relative_to(PROJECT_ROOT), imported)
                )
    assert not violations, "Dependency boundary violations:\n{}".format(
        "\n".join(violations)
    )


def test_core_contracts_do_not_depend_on_frameworks_or_integrations() -> None:
    _assert_imports_exclude(
        _python_files(
            SOURCE_ROOT / "camera_system" / "domain",
            SOURCE_ROOT / "camera_system" / "interfaces.py",
        ),
        {
            "PyQt5",
            "PySide6",
            "camera_system_app",
            "multiwebcam",
            "q3dviewer",
            "tx_rx",
        },
    )


def test_application_domain_does_not_depend_on_outer_layers() -> None:
    _assert_imports_exclude(
        _python_files(SOURCE_ROOT / "camera_system_app" / "domain"),
        {
            "PyQt5",
            "PySide6",
            "camera_system_app.application",
            "camera_system_app.config",
            "camera_system_app.infrastructure",
            "camera_system_app.ui",
            "camera_system_app.workers",
            "multiwebcam",
            "q3dviewer",
            "tx_rx",
        },
    )


def test_application_services_do_not_import_widgets() -> None:
    _assert_imports_exclude(
        _python_files(SOURCE_ROOT / "camera_system_app" / "application"),
        {
            "PyQt5.QtGui",
            "PyQt5.QtWidgets",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "camera_system_app.ui",
        },
    )
