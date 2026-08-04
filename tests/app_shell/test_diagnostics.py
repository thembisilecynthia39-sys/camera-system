from types import SimpleNamespace

from camera_system_app.application import diagnostics as diagnostics_module
from camera_system_app.application.diagnostics import DiagnosticService
from camera_system_app.domain.diagnostics import DiagnosticStatus


def _service() -> DiagnosticService:
    return DiagnosticService(
        paths=SimpleNamespace(),
        settings=SimpleNamespace(),
    )


def test_project_dependency_check_fails_for_missing_core_module(monkeypatch):
    def find_spec(name):
        return None if name == "numpy" else SimpleNamespace(origin=name)

    monkeypatch.setattr(diagnostics_module.importlib.util, "find_spec", find_spec)

    check = _service()._dependency_check()

    assert check.status is DiagnosticStatus.FAILURE
    assert "numpy" in check.detail


def test_project_dependency_check_only_warns_for_missing_optional_tools(
    monkeypatch,
):
    optional = {"qfluentwidgets", "onnx"}

    def find_spec(name):
        return None if name in optional else SimpleNamespace(origin=name)

    monkeypatch.setattr(diagnostics_module.importlib.util, "find_spec", find_spec)

    check = _service()._dependency_check()

    assert check.status is DiagnosticStatus.WARNING
    assert "核心运行依赖可用" in check.summary
    assert "qfluentwidgets" in check.detail
    assert "onnx" in check.detail
