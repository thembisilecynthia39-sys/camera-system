from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_inference_service_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "inference_service.py"
    spec = importlib.util.spec_from_file_location("test_inference_service_module", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disable_torchvision_nms_removes_top_level_module():
    module = _load_inference_service_module()
    sys.modules["torchvision"] = object()

    module._UltralyticsTensorRTDetector._disable_torchvision_nms()

    assert "torchvision" not in sys.modules
