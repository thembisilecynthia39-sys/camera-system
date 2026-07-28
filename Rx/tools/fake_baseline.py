#!/usr/bin/env python3
"""Write a deterministic small PLY at the exact path expected by the Rx worker."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    task_id = os.environ["SCENE_NAME"]
    run_name = os.environ["RUN_NAME"]
    iterations = int(sys.argv[3])
    output = (
        Path(os.environ["OUT_ROOT"])
        / task_id
        / f"{run_name}_shsharp_scale101"
        / "point_cloud"
        / f"iteration_{iterations}"
        / "point_cloud.ply"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n"
    output.write_bytes(payload)
    print("training one baseline model", flush=True)
    print(f"fake PLY written to {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
