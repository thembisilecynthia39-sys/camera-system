"""Prepare deterministic baseline input and output paths for one task."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from gaussianobject_rx.protocol.models import TASK_FILENAMES
from gaussianobject_rx.server.files import atomic_write_json


class BaselineInputError(Exception):
    """A validated task cannot be adapted to baseline input."""


@dataclass(frozen=True)
class BaselineInvocation:
    command: List[str]
    environment: Dict[str, str]
    expected_output_ply: Path
    log_path: Path


def prepare_baseline_input(
    package_dir: Path,
    task_dir: Path,
    image_dimensions: Dict[str, Tuple[int, int]],
) -> Path:
    """Create input/images atomically, preserving normalized JPEG names."""

    final_root = task_dir / "input"
    if final_root.is_dir():
        return final_root / "images"
    temporary = task_dir / ".input.part"
    shutil.rmtree(temporary, ignore_errors=True)
    images = temporary / "images"
    images.mkdir(parents=True)
    try:
        for filename in TASK_FILENAMES:
            source = package_dir / "images" / filename
            destination = images / filename
            if not source.is_file():
                raise BaselineInputError(f"missing normalized image: {filename}")
            try:
                os.link(str(source), str(destination))
            except OSError:
                shutil.copy2(source, destination)
        unique_resolutions = sorted({f"{width}x{height}" for width, height in image_dimensions.values()})
        atomic_write_json(
            temporary / "input.json",
            {
                "image_count": len(TASK_FILENAMES),
                "images": TASK_FILENAMES,
                "image_format": "jpeg",
                "resolutions": unique_resolutions,
                "mixed_resolutions": len(unique_resolutions) > 1,
            },
        )
        temporary.rename(final_root)
        return final_root / "images"
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def build_baseline_invocation(
    task_id: str,
    task_dir: Path,
    baseline_path: Path,
    iterations: int,
) -> BaselineInvocation:
    input_images = task_dir / "input" / "images"
    output_root = task_dir / "reconstruction"
    data_root = task_dir / "prepared"
    run_name = f"baseline_i{iterations}"
    expected = (
        output_root
        / task_id
        / f"{run_name}_shsharp_scale101"
        / "point_cloud"
        / f"iteration_{iterations}"
        / "point_cloud.ply"
    )
    environment = {
        "SCENE_NAME": task_id,
        "RUN_TAG": task_id,
        "RUN_NAME": run_name,
        "DATA_ROOT": str(data_root),
        "OUT_ROOT": str(output_root),
    }
    return BaselineInvocation(
        command=[str(baseline_path), str(input_images), "8", str(iterations)],
        environment=environment,
        expected_output_ply=expected,
        log_path=task_dir / "reconstruction.log",
    )
