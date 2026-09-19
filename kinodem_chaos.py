#!/usr/bin/env python3
"""
KinoDEM chaos twin experiment.

Runs two real LIGGGHTS cases with identical particle positions/velocities except
for a microscopic perturbation to one velocity component. It measures how the
state separation grows with time.

A positive fitted log-slope is a finite-time divergence diagnostic. It is not,
by itself, proof of a universal Lyapunov exponent for the real Kino machine.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from kinodem_liggghts import (
    LiggghtsConfig,
    N_BALLS,
    default_ball_calibration,
    generate_initial_state,
    prepare_case,
    run_case,
)


def parse_dump_trajectory(path: str | Path) -> dict[int, dict[str, np.ndarray]]:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    out: dict[int, dict[str, np.ndarray]] = {}
    i = 0
    while i < len(lines):
        if lines[i].strip() != "ITEM: TIMESTEP":
            i += 1
            continue
        step = int(lines[i + 1].strip())
        if lines[i + 2].strip() != "ITEM: NUMBER OF ATOMS":
            raise ValueError("unexpected dump format after timestep")
        n = int(lines[i + 3].strip())
        if n != N_BALLS:
            raise ValueError(f"expected {N_BALLS} atoms, got {n}")
        if not lines[i + 4].startswith("ITEM: BOX BOUNDS"):
            raise ValueError("missing BOX BOUNDS")
        atom_header = i + 8
        if not lines[atom_header].startswith("ITEM: ATOMS"):
            raise ValueError("missing ATOMS header")
        cols = lines[atom_header].split()[2:]
        needed = {"id", "x", "y", "z", "vx", "vy", "vz"}
        if not needed.issubset(cols):
            raise ValueError(f"dump missing columns {sorted(needed-set(cols))}")
        col = {name: idx for idx, name in enumerate(cols)}
        pos = np.zeros((N_BALLS, 3), dtype=float)
        vel = np.zeros((N_BALLS, 3), dtype=float)
        for k in range(N_BALLS):
            parts = lines[atom_header + 1 + k].split()
            atom_id = int(float(parts[col["id"]]))
            if not 1 <= atom_id <= N_BALLS:
                raise ValueError(f"invalid atom id {atom_id}")
            idx = atom_id - 1
            pos[idx] = [float(parts[col[q]]) for q in ("x", "y", "z")]
            vel[idx] = [float(parts[col[q]]) for q in ("vx", "vy", "vz")]
        out[step] = {"pos": pos, "vel": vel}
        i = atom_header + 1 + N_BALLS
    if not out:
        raise ValueError("no dump frames found")
    return out


def divergence_series(
    a: dict[int, dict[str, np.ndarray]],
    b: dict[int, dict[str, np.ndarray]],
    timestep: float,
) -> list[dict[str, float]]:
    steps = sorted(set(a) & set(b))
    if not steps:
        raise ValueError("twin trajectories have no common timesteps")
    rows = []
    for step in steps:
        dp = b[step]["pos"] - a[step]["pos"]
        dv = b[step]["vel"] - a[step]["vel"]
        pos_rms = float(np.sqrt(np.mean(np.sum(dp * dp, axis=1))))
        vel_rms = float(np.sqrt(np.mean(np.sum(dv * dv, axis=1))))
        max_pos = float(np.max(np.linalg.norm(dp, axis=1)))
        rows.append({
            "step": int(step),
            "time_s": float(step * timestep),
            "position_rms_m": pos_rms,
            "velocity_rms_m_s": vel_rms,
            "max_particle_position_separation_m": max_pos,
        })
    return rows


def fit_log_divergence(
    rows: list[dict[str, float]],
    min_value: float = 1e-12,
    max_value: float | None = None,
) -> dict[str, float | int | None]:
    pts = []
    for r in rows:
        d = float(r["position_rms_m"])
        if d <= min_value:
            continue
        if max_value is not None and d >= max_value:
            continue
        pts.append((float(r["time_s"]), d))
    if len(pts) < 5:
        return {"n_fit": len(pts), "lambda_1_s": None, "r2": None}
    t = np.asarray([p[0] for p in pts], dtype=float)
    y = np.log(np.asarray([p[1] for p in pts], dtype=float))
    slope, intercept = np.polyfit(t, y, 1)
    pred = slope * t + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return {"n_fit": len(pts), "lambda_1_s": float(slope), "r2": float(r2)}


def run_twin_experiment(
    root: str | Path,
    cfg: LiggghtsConfig,
    seed: int,
    liggghts: str,
    velocity_epsilon: float = 1e-6,
    ball_number: int = 1,
    axis: int = 0,
) -> dict:
    if velocity_epsilon <= 0 or not math.isfinite(velocity_epsilon):
        raise ValueError("velocity_epsilon must be positive and finite")
    if not 1 <= ball_number <= N_BALLS:
        raise ValueError("ball_number must be 1..25")
    if axis not in (0, 1, 2):
        raise ValueError("axis must be 0, 1 or 2")

    if cfg.dump_every_steps <= 0:
        cfg = replace(cfg, dump_every_steps=max(1, cfg.steps // 100))

    specs = default_ball_calibration(cfg)
    pos, vel = generate_initial_state(cfg, seed, specs)
    vel_b = vel.copy()
    vel_b[ball_number - 1, axis] += velocity_epsilon

    root = Path(root)
    case_a = prepare_case(root / "twin_A", cfg, seed, specs, initial_state=(pos, vel))
    case_b = prepare_case(root / "twin_B", cfg, seed, specs, initial_state=(pos, vel_b))
    run_case(case_a, liggghts)
    run_case(case_b, liggghts)

    traj_a = parse_dump_trajectory(case_a / "state.dump")
    traj_b = parse_dump_trajectory(case_b / "state.dump")
    rows = divergence_series(traj_a, traj_b, cfg.timestep)

    fit = fit_log_divergence(
        rows,
        min_value=max(1e-14, velocity_epsilon * cfg.timestep * 1e-3),
        max_value=cfg.drum_radius * 0.20,
    )

    csv_path = root / "divergence.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    nonzero = [r for r in rows if r["position_rms_m"] > 0]
    first_nonzero = nonzero[0]["position_rms_m"] if nonzero else 0.0
    final = rows[-1]
    amplification = (
        float(final["position_rms_m"] / first_nonzero)
        if first_nonzero > 0 else None
    )
    result = {
        "backend": "LIGGGHTS-PUBLIC",
        "seed": seed,
        "velocity_epsilon_m_s": velocity_epsilon,
        "perturbed_ball": ball_number,
        "perturbed_axis": axis,
        "frames": len(rows),
        "duration_s": final["time_s"],
        "initial_nonzero_position_rms_m": first_nonzero,
        "final_position_rms_m": final["position_rms_m"],
        "final_velocity_rms_m_s": final["velocity_rms_m_s"],
        "position_amplification": amplification,
        "finite_time_fit": fit,
        "config": asdict(cfg),
        "stability_A": json.loads((case_a / "stability.json").read_text()),
        "stability_B": json.loads((case_b / "stability.json").read_text()),
    }
    (root / "chaos_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="KinoDEM LIGGGHTS twin-chaos experiment")
    ap.add_argument("--workdir", default="kinodem-chaos")
    ap.add_argument("--seed", type=int, default=20260919)
    ap.add_argument("--seconds", type=float, default=0.20)
    ap.add_argument("--dt", type=float, default=1e-5)
    ap.add_argument("--dump-every", type=int, default=100)
    ap.add_argument("--epsilon-v", type=float, default=1e-6)
    ap.add_argument("--ball", type=int, default=1)
    ap.add_argument("--axis", type=int, choices=[0, 1, 2], default=0)
    ap.add_argument("--omega", type=float, default=7.0)
    ap.add_argument("--liggghts", required=True)
    args = ap.parse_args()

    cfg = LiggghtsConfig(
        geometry="globe",
        seconds=args.seconds,
        timestep=args.dt,
        dump_every_steps=args.dump_every,
        angular_velocity=args.omega,
    )
    result = run_twin_experiment(
        args.workdir,
        cfg,
        args.seed,
        args.liggghts,
        velocity_epsilon=args.epsilon_v,
        ball_number=args.ball,
        axis=args.axis,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
