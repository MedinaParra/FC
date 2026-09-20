#!/usr/bin/env python3
"""
KinoCFDDEM v4
=============

Adds an explicit, parameterized *virtual capture throat* to the already
validated two-way OpenFOAM/CFDEM/LIGGGHTS surrogate model from v3.

The throat is a measurement/capture zone INSIDE the closed CFD domain. This is
deliberate: letting particles leave the CFD mesh can invalidate cfdemSolverIB's
particle-location contract. v4 therefore detects ordered first-entry events
without pretending that the real Kino extraction hardware is already known.

A later calibrated version can replace this virtual throat with a measured
physical outlet/nozzle geometry.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from kinodem_cfdem_case import CFDDEMConfig, validate_case, write_case
from kinodem_chaos import parse_dump_trajectory

N_BALLS = 25
N_DRAW = 14


@dataclass(frozen=True)
class CaptureConfig:
    axis_x: float = 0.0
    axis_y: float = 0.0
    axis_z: float = 1.0
    port_radius_m: float = 0.050
    sensor_depth_m: float = 0.060
    min_outward_velocity_m_s: float = 0.0
    require_transition: bool = True

    def axis(self) -> np.ndarray:
        a = np.asarray([self.axis_x, self.axis_y, self.axis_z], dtype=float)
        n = float(np.linalg.norm(a))
        if not math.isfinite(n) or n <= 0:
            raise ValueError("capture axis must be finite and non-zero")
        return a / n

    def validate(self, chamber_radius_m: float, ball_radius_m: float) -> None:
        self.axis()
        if not (ball_radius_m < self.port_radius_m < chamber_radius_m):
            raise ValueError(
                "port_radius_m must be larger than one ball radius and smaller "
                "than the chamber radius"
            )
        if not (0.0 < self.sensor_depth_m < chamber_radius_m):
            raise ValueError("sensor_depth_m must be within the chamber radius")
        if not math.isfinite(self.min_outward_velocity_m_s):
            raise ValueError("min_outward_velocity_m_s must be finite")

    def sensor_plane_offset(self, chamber_radius_m: float) -> float:
        return chamber_radius_m - self.sensor_depth_m

    def effective_center_radius(self, ball_radius_m: float) -> float:
        # Centerline clearance: the whole sphere must fit through the idealized
        # circular throat rather than only its center.
        return self.port_radius_m - ball_radius_m


def _orthonormal_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    trial = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(trial, axis))) > 0.9:
        trial = np.array([0.0, 1.0, 0.0])
    e1 = trial - np.dot(trial, axis) * axis
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    e2 /= np.linalg.norm(e2)
    return e1, e2


def extraction_probe_points(
    cfd_cfg: CFDDEMConfig,
    capture: CaptureConfig,
) -> list[np.ndarray]:
    capture.validate(cfd_cfg.globe_radius_m, cfd_cfg.ball_radius_m)
    a = capture.axis()
    e1, e2 = _orthonormal_basis(a)
    s = capture.sensor_plane_offset(cfd_cfg.globe_radius_m)
    center = a * s
    r = capture.effective_center_radius(cfd_cfg.ball_radius_m) * 0.60
    return [
        center,
        center + r * e1,
        center - r * e1,
        center + r * e2,
        center - r * e2,
    ]


def _foam_probe_block(points: list[np.ndarray]) -> str:
    locs = "\n".join(
        f"            ({p[0]:.12g} {p[1]:.12g} {p[2]:.12g})"
        for p in points
    )
    return f"""

functions
{{
    extractionProbes
    {{
        type probes;
        libs ("libsampling.so");
        writeControl timeStep;
        writeInterval 1;
        fields (p U voidfraction);
        probeLocations
        (
{locs}
        );
    }}
}}
"""


def write_v4_case(
    root: str | Path,
    cfd_cfg: CFDDEMConfig,
    capture: CaptureConfig | None = None,
) -> Path:
    capture = capture or CaptureConfig()
    capture.validate(cfd_cfg.globe_radius_m, cfd_cfg.ball_radius_m)
    root = write_case(root, cfd_cfg)

    extraction = {
        "model": "virtual_capture_throat",
        "status": "surrogate_not_real_hardware_geometry",
        "axis_unit": capture.axis().tolist(),
        "port_radius_m": capture.port_radius_m,
        "sensor_depth_m": capture.sensor_depth_m,
        "sensor_plane_offset_m": capture.sensor_plane_offset(cfd_cfg.globe_radius_m),
        "effective_center_radius_m": capture.effective_center_radius(
            cfd_cfg.ball_radius_m
        ),
        "min_outward_velocity_m_s": capture.min_outward_velocity_m_s,
        "require_transition": capture.require_transition,
        "event_definition": (
            "first inward-to-capture-zone transition of each unique ball while "
            "moving along the outlet axis"
        ),
        "without_replacement_observation": True,
        "without_replacement_physics": False,
        "required_unique_events": N_DRAW,
    }
    (root / "extraction_config.json").write_text(
        json.dumps(extraction, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    probes = extraction_probe_points(cfd_cfg, capture)
    control = root / "CFD" / "system" / "controlDict"
    txt = control.read_text(encoding="utf-8")
    if "extractionProbes" not in txt:
        control.write_text(txt + _foam_probe_block(probes), encoding="utf-8")

    manifest_path = root / "case_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model"] = "KinoCFDDEM v4"
    manifest["capture_model"] = extraction
    manifest["official_draw_contract"] = {
        "balls_loaded": 25,
        "unique_balls_required": 14,
        "replacement": False,
        "order_used_for_prize_matching": False,
    }
    manifest["v4_limitations"] = [
        "capture throat dimensions and direction are surrogate parameters",
        "captured particles are observed/deduplicated but are not physically removed",
        "real extraction hardware and airflow law require video/measurement calibration",
    ]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return root


def validate_v4_case(root: str | Path) -> dict:
    root = Path(root)
    base = validate_case(root)
    ep = root / "extraction_config.json"
    if not ep.exists():
        raise ValueError("missing extraction_config.json")
    extraction = json.loads(ep.read_text(encoding="utf-8"))
    if extraction["required_unique_events"] != N_DRAW:
        raise ValueError("capture model must require exactly 14 unique events")
    control = (root / "CFD" / "system" / "controlDict").read_text(encoding="utf-8")
    if "extractionProbes" not in control:
        raise ValueError("OpenFOAM extraction probes are missing")
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("model") != "KinoCFDDEM v4":
        raise ValueError("v4 manifest marker missing")
    return {
        "ok": True,
        "base": base,
        "extraction": extraction,
        "probe_count": 5,
    }


def _capture_membership(
    pos: np.ndarray,
    vel: np.ndarray,
    cfd_cfg: CFDDEMConfig,
    capture: CaptureConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = capture.axis()
    s = pos @ a
    radial_vec = pos - np.outer(s, a)
    radial = np.linalg.norm(radial_vec, axis=1)
    axial_v = vel @ a
    inside = (
        (s >= capture.sensor_plane_offset(cfd_cfg.globe_radius_m))
        & (radial <= capture.effective_center_radius(cfd_cfg.ball_radius_m))
    )
    moving_out = axial_v >= capture.min_outward_velocity_m_s
    return inside, moving_out, axial_v


def detect_capture_events(
    trajectory: dict[int, dict[str, np.ndarray]],
    dem_dt_s: float,
    cfd_cfg: CFDDEMConfig,
    capture: CaptureConfig,
) -> list[dict]:
    if dem_dt_s <= 0:
        raise ValueError("dem_dt_s must be positive")
    capture.validate(cfd_cfg.globe_radius_m, cfd_cfg.ball_radius_m)
    steps = sorted(trajectory)
    if not steps:
        raise ValueError("trajectory is empty")

    first = trajectory[steps[0]]
    prev_inside, _, _ = _capture_membership(
        first["pos"], first["vel"], cfd_cfg, capture
    )
    seen: set[int] = set()
    events: list[dict] = []

    for step in steps[1:]:
        frame = trajectory[step]
        inside, moving_out, axial_v = _capture_membership(
            frame["pos"], frame["vel"], cfd_cfg, capture
        )
        if capture.require_transition:
            candidates = inside & ~prev_inside & moving_out
        else:
            candidates = inside & moving_out

        ids = np.flatnonzero(candidates)
        # If multiple balls cross between two stored frames, order the same-frame
        # candidates by deeper axial penetration as a deterministic tie-breaker.
        if len(ids):
            a = capture.axis()
            proj = frame["pos"][ids] @ a
            ids = ids[np.argsort(proj)[::-1]]

        for idx in ids:
            number = int(idx + 1)
            if number in seen:
                continue
            seen.add(number)
            pos = frame["pos"][idx]
            events.append({
                "event_index": len(events) + 1,
                "number": number,
                "step": int(step),
                "time_s": float(step * dem_dt_s),
                "x_m": float(pos[0]),
                "y_m": float(pos[1]),
                "z_m": float(pos[2]),
                "axial_velocity_m_s": float(axial_v[idx]),
            })
        prev_inside = inside
    return events


def summarize_extraction(events: list[dict]) -> dict:
    first14 = events[:N_DRAW]
    complete = len(first14) == N_DRAW
    return {
        "unique_capture_events": len(events),
        "complete_14": complete,
        "ordered_numbers_observed": [e["number"] for e in events],
        "first_14": [e["number"] for e in first14],
        "time_to_14_s": first14[-1]["time_s"] if complete else None,
        "interpretation": (
            "virtual capture-throat event ordering; not yet a calibrated real-Kino "
            "extraction sequence"
        ),
        "without_replacement_observation": True,
        "without_replacement_physics": False,
    }


def analyze_dump(
    dump_path: str | Path,
    outdir: str | Path,
    cfd_cfg: CFDDEMConfig,
    capture: CaptureConfig,
) -> dict:
    trajectory = parse_dump_trajectory(dump_path)
    events = detect_capture_events(
        trajectory, cfd_cfg.dem_dt_s, cfd_cfg, capture
    )
    summary = summarize_extraction(events)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "event_index","number","step","time_s","x_m","y_m","z_m",
        "axial_velocity_m_s",
    ]
    with (outdir / "extraction_events.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(events)

    payload = {
        "summary": summary,
        "capture": asdict(capture),
        "cfd_config": asdict(cfd_cfg),
    }
    (outdir / "extraction_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def aggregate_capture_summaries(paths: Iterable[str | Path]) -> dict:
    counts = np.zeros(N_BALLS, dtype=int)
    complete_runs = 0
    total_runs = 0
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        total_runs += 1
        first14 = data["summary"]["first_14"]
        if data["summary"]["complete_14"]:
            complete_runs += 1
        for number in set(first14):
            counts[int(number) - 1] += 1

    denom = complete_runs if complete_runs else 0
    probs = (
        (counts / float(denom)).tolist()
        if denom > 0
        else [None] * N_BALLS
    )
    return {
        "runs": total_runs,
        "complete_runs": complete_runs,
        "incomplete_runs": total_runs - complete_runs,
        "counts_in_first14_complete_runs": counts.tolist(),
        "inclusion_probabilities_complete_runs": probs,
        "baseline_if_symmetric": N_DRAW / N_BALLS,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="KinoCFDDEM v4 capture-throat model")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--out", default="kinocfdem-v4-case")
    g.add_argument("--end-time", type=float, default=0.02)
    g.add_argument("--omega", type=float, default=7.0)
    g.add_argument("--base-cells", type=int, default=32)
    g.add_argument("--port-radius", type=float, default=0.050)
    g.add_argument("--sensor-depth", type=float, default=0.060)

    a = sub.add_parser("analyze")
    a.add_argument("dump")
    a.add_argument("--outdir", default="kinocfdem-v4-extraction")
    a.add_argument("--dem-dt", type=float, default=1e-5)
    a.add_argument("--chamber-radius", type=float, default=0.25)
    a.add_argument("--ball-radius", type=float, default=0.020)
    a.add_argument("--port-radius", type=float, default=0.050)
    a.add_argument("--sensor-depth", type=float, default=0.060)
    a.add_argument("--min-outward-velocity", type=float, default=0.0)

    args = ap.parse_args()

    if args.cmd == "generate":
        cfd = CFDDEMConfig(
            end_time_s=args.end_time,
            omega_rad_s=args.omega,
            base_cells=args.base_cells,
        )
        cap = CaptureConfig(
            port_radius_m=args.port_radius,
            sensor_depth_m=args.sensor_depth,
        )
        root = write_v4_case(args.out, cfd, cap)
        print(json.dumps(validate_v4_case(root), indent=2))
    else:
        cfd = CFDDEMConfig(
            globe_radius_m=args.chamber_radius,
            ball_radius_m=args.ball_radius,
            dem_dt_s=args.dem_dt,
            end_time_s=max(0.001, args.dem_dt * 2),
        )
        cap = CaptureConfig(
            port_radius_m=args.port_radius,
            sensor_depth_m=args.sensor_depth,
            min_outward_velocity_m_s=args.min_outward_velocity,
        )
        result = analyze_dump(args.dump, args.outdir, cfd, cap)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
