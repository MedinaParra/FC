#!/usr/bin/env python3
"""KinoCFDDEM v4.1 real-machine calibration wrapper.

v4.1 does NOT pretend that the agitation law is known.  The user-provided
Kino 3281 screenshots remove the old rotating-wall hypothesis from the
real-machine baseline.  This wrapper therefore generates a stationary-wall
diagnostic case (omega = 0) while preserving the proven v4 coupling stack.

It is a geometry/coupling baseline, not yet a draw-reconstruction run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kinodem_cfdem_case import CFDDEMConfig
from kinocfdem_v4 import CaptureConfig, validate_v4_case, write_v4_case

CALIBRATION_FILE = Path("calibration/kino3281_screenshot_calibration.json")


def write_v41_case(
    root: str | Path,
    end_time_s: float = 0.02,
    base_cells: int = 32,
    port_radius_m: float = 0.050,
    sensor_depth_m: float = 0.060,
) -> Path:
    cfd = CFDDEMConfig(
        omega_rad_s=0.0,
        end_time_s=end_time_s,
        base_cells=base_cells,
    )
    capture = CaptureConfig(
        port_radius_m=port_radius_m,
        sensor_depth_m=sensor_depth_m,
    )
    root = write_v4_case(root, cfd, capture)
    root = Path(root)
    manifest_path = root / "case_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["variant"] = "KinoCFDDEM v4.1 screenshot-calibrated baseline"
    manifest["machine_calibration"] = {
        "evidence": str(CALIBRATION_FILE),
        "draw": 3281,
        "wall_motion": "stationary",
        "implementation": "legacy rotating-wall BC/mesh law with omega=0",
        "agitation_driver": "unresolved non-wall forcing",
        "forced_air_status": "candidate_not_measured",
        "projected_outer_D_over_ball_d": 14.321012472804588,
        "absolute_scale_identified": False,
        "temporal_velocity_identified": False,
    }
    manifest["v41_guardrail"] = (
        "This stationary case is a diagnostic geometry/coupling baseline. "
        "Do not describe it as a calibrated mixing simulation until the "
        "non-wall agitation field is identified from timed video or machine data."
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return root


def validate_v41_case(root: str | Path) -> dict:
    root = Path(root)
    base = validate_v4_case(root)
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    cal = manifest.get("machine_calibration", {})
    if manifest.get("model") != "KinoCFDDEM v4.1 screenshot-calibrated baseline":
        raise ValueError("v4.1 manifest marker missing")
    if cal.get("wall_motion") != "stationary":
        raise ValueError("v4.1 real-machine baseline must be stationary")
    if float(manifest["config"]["omega_rad_s"]) != 0.0:
        raise ValueError("v4.1 real-machine baseline must have omega=0")
    if cal.get("agitation_driver") != "unresolved non-wall forcing":
        raise ValueError("v4.1 must preserve unresolved agitation status")
    return {"ok": True, "base": base, "machine_calibration": cal}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="kinocfdem-v4.1-static-baseline")
    ap.add_argument("--end-time", type=float, default=0.02)
    ap.add_argument("--base-cells", type=int, default=32)
    ap.add_argument("--port-radius", type=float, default=0.050)
    ap.add_argument("--sensor-depth", type=float, default=0.060)
    args = ap.parse_args()
    root = write_v41_case(
        args.out,
        end_time_s=args.end_time,
        base_cells=args.base_cells,
        port_radius_m=args.port_radius,
        sensor_depth_m=args.sensor_depth,
    )
    print(json.dumps(validate_v41_case(root), indent=2))


if __name__ == "__main__":
    main()
