#!/usr/bin/env python3
"""
KinoDEM v2 - LIGGGHTS backend
=============================

Generates and optionally runs a 3D LIGGGHTS-PUBLIC model for 25 numbered
Kino balls in a rotating cylindrical drum. Geometry/material constants are
surrogate values until real machine measurements are available.

Ball IDs 1..25 are the lottery numbers. The final 14-number selection is a
post-processing outlet score over the final DEM state; it is not yet a model
of the real extraction mechanism.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

import numpy as np

N_BALLS = 25
N_DRAW = 14


@dataclass(frozen=True)
class LiggghtsConfig:
    drum_radius: float = 0.25
    drum_depth: float = 0.12
    drum_segments: int = 72
    ball_radius: float = 0.020
    ball_density: float = 900.0
    youngs_modulus: float = 5.0e6
    poisson_ratio: float = 0.45
    restitution: float = 0.82
    friction: float = 0.18
    angular_velocity: float = 7.0
    gravity: float = 9.81
    timestep: float = 1.0e-5
    seconds: float = 0.10
    outlet_angle_deg: float = 90.0
    outlet_velocity_weight: float = 0.025

    def validate(self) -> None:
        if self.drum_radius <= 3 * self.ball_radius:
            raise ValueError("drum_radius too small for configured ball_radius")
        if self.drum_depth <= 2.2 * self.ball_radius:
            raise ValueError("drum_depth too small for configured ball_radius")
        if self.drum_segments < 16:
            raise ValueError("drum_segments must be >= 16")
        if self.timestep <= 0 or self.seconds <= 0:
            raise ValueError("timestep and seconds must be positive")
        if self.ball_density <= 0 or self.youngs_modulus <= 0:
            raise ValueError("material parameters must be positive")
        if not (0 <= self.restitution <= 1):
            raise ValueError("restitution must be within [0,1]")
        if self.friction < 0:
            raise ValueError("friction must be non-negative")

    @property
    def steps(self) -> int:
        return max(1, int(round(self.seconds / self.timestep)))


@dataclass(frozen=True)
class MonteCarloPerturbation:
    radius_sigma_frac: float = 0.0025
    density_sigma_frac: float = 0.005
    restitution_sigma: float = 0.01
    friction_sigma: float = 0.01
    omega_sigma_frac: float = 0.01


def _facet(normal: Iterable[float], a: Iterable[float], b: Iterable[float], c: Iterable[float]) -> str:
    n = tuple(float(x) for x in normal)
    pts = [tuple(float(x) for x in p) for p in (a, b, c)]
    return (
        f"  facet normal {n[0]:.12g} {n[1]:.12g} {n[2]:.12g}\n"
        "    outer loop\n"
        + "".join(f"      vertex {p[0]:.12g} {p[1]:.12g} {p[2]:.12g}\n" for p in pts)
        + "    endloop\n  endfacet\n"
    )


def write_drum_stl(path: str | Path, cfg: LiggghtsConfig) -> Path:
    cfg.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    r = cfg.drum_radius
    z0, z1 = -cfg.drum_depth / 2.0, cfg.drum_depth / 2.0
    seg = cfg.drum_segments

    chunks = ["solid kinodem_drum\n"]
    for k in range(seg):
        a0 = 2 * math.pi * k / seg
        a1 = 2 * math.pi * (k + 1) / seg
        p00 = (r * math.cos(a0), r * math.sin(a0), z0)
        p01 = (r * math.cos(a0), r * math.sin(a0), z1)
        p10 = (r * math.cos(a1), r * math.sin(a1), z0)
        p11 = (r * math.cos(a1), r * math.sin(a1), z1)
        amid = (a0 + a1) / 2.0
        nside = (math.cos(amid), math.sin(amid), 0.0)
        chunks.append(_facet(nside, p00, p10, p11))
        chunks.append(_facet(nside, p00, p11, p01))
        chunks.append(_facet((0.0, 0.0, -1.0), (0, 0, z0), p10, p00))
        chunks.append(_facet((0.0, 0.0, 1.0), (0, 0, z1), p01, p11))
    chunks.append("endsolid kinodem_drum\n")
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def generate_initial_state(cfg: LiggghtsConfig, seed: int) -> tuple[np.ndarray, np.ndarray]:
    cfg.validate()
    rng = np.random.default_rng(seed)
    pos = np.zeros((N_BALLS, 3), dtype=float)
    vel = rng.normal(0.0, 0.08, size=(N_BALLS, 3))
    margin = 1e-4
    radial_limit = cfg.drum_radius - cfg.ball_radius - margin
    z_limit = cfg.drum_depth / 2 - cfg.ball_radius - margin
    min_sep = 2 * cfg.ball_radius + 2e-4

    for i in range(N_BALLS):
        for _ in range(100_000):
            rho = radial_limit * math.sqrt(float(rng.random()))
            theta = float(rng.uniform(0.0, 2 * math.pi))
            z = float(rng.uniform(-z_limit, z_limit))
            cand = np.array([rho * math.cos(theta), rho * math.sin(theta), z])
            if i == 0 or np.all(np.linalg.norm(pos[:i] - cand, axis=1) > min_sep):
                pos[i] = cand
                break
        else:
            raise RuntimeError("could not place all 25 balls without overlap")
    return pos, vel


def write_ball_data(path: str | Path, cfg: LiggghtsConfig, seed: int) -> Path:
    cfg.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pos, vel = generate_initial_state(cfg, seed)
    pad = 0.05
    xy = cfg.drum_radius + pad
    zbox = cfg.drum_depth / 2 + pad

    lines = [
        "KinoDEM v2 LIGGGHTS data - surrogate parameters\n\n",
        f"{N_BALLS} atoms\n",
        "1 atom types\n\n",
        f"{-xy:.12g} {xy:.12g} xlo xhi\n",
        f"{-xy:.12g} {xy:.12g} ylo yhi\n",
        f"{-zbox:.12g} {zbox:.12g} zlo zhi\n\n",
        "Atoms\n\n",
    ]
    diameter = 2 * cfg.ball_radius
    for i in range(N_BALLS):
        x, y, z = pos[i]
        lines.append(
            f"{i+1} 1 {diameter:.12g} {cfg.ball_density:.12g} "
            f"{x:.12g} {y:.12g} {z:.12g}\n"
        )
    lines.append("\nVelocities\n\n")
    for i in range(N_BALLS):
        vx, vy, vz = vel[i]
        lines.append(f"{i+1} {vx:.12g} {vy:.12g} {vz:.12g} 0 0 0\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def write_liggghts_input(path: str | Path, cfg: LiggghtsConfig) -> Path:
    cfg.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_every = max(1, cfg.steps)
    txt = f"""# KinoDEM v2 - LIGGGHTS-PUBLIC physical surrogate
atom_style sphere
atom_modify map array sort 0 0
boundary f f f
newton off
communicate single vel yes
units si

read_data balls.data

neighbor 0.004 bin
neigh_modify delay 0

# Surrogate properties: calibrate against the real machine before interpreting physically.
fix m1 all property/global youngsModulus peratomtype {cfg.youngs_modulus:.12g}
fix m2 all property/global poissonsRatio peratomtype {cfg.poisson_ratio:.12g}
fix m3 all property/global coefficientRestitution peratomtypepair 1 {cfg.restitution:.12g}
fix m4 all property/global coefficientFriction peratomtypepair 1 {cfg.friction:.12g}

pair_style gran model hertz tangential history
pair_coeff * *

# Static symmetric mesh + rotating surface velocity.
fix drum all mesh/surface file drum.stl type 1 surface_ang_vel origin 0 0 0 axis 0 0 1 omega {cfg.angular_velocity:.12g}
fix wall all wall/gran model hertz tangential history mesh n_meshes 1 meshes drum

fix grav all gravity {cfg.gravity:.12g} vector 0 -1 0
fix integr all nve/sphere

timestep {cfg.timestep:.12g}
thermo_style custom step atoms ke
thermo {max(1, cfg.steps // 10)}
thermo_modify lost error norm no

dump state all custom {dump_every} state.dump id type x y z vx vy vz omegax omegay omegaz radius
dump_modify state sort id

run {cfg.steps}
"""
    path.write_text(txt, encoding="utf-8")
    return path


def prepare_case(workdir: str | Path, cfg: LiggghtsConfig, seed: int) -> Path:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    write_drum_stl(workdir / "drum.stl", cfg)
    write_ball_data(workdir / "balls.data", cfg, seed)
    write_liggghts_input(workdir / "in.kinodem", cfg)
    (workdir / "case.json").write_text(
        json.dumps({"seed": seed, "config": asdict(cfg)}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return workdir


def find_liggghts(explicit: str | None = None) -> str:
    candidates = [explicit, os.environ.get("LIGGGHTS_BIN"), "liggghts", "lmp_auto", "lmp_serial"]
    for c in candidates:
        if not c:
            continue
        p = shutil.which(c) if os.path.sep not in c else c
        if p and Path(p).exists():
            return str(Path(p).resolve())
    raise FileNotFoundError("LIGGGHTS executable not found; pass --liggghts or set LIGGGHTS_BIN")


def run_case(workdir: str | Path, liggghts: str | None = None, timeout: int = 600):
    workdir = Path(workdir)
    exe = find_liggghts(liggghts)
    proc = subprocess.run(
        [exe, "-in", "in.kinodem"],
        cwd=workdir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    log_path = workdir / "liggghts.stdout.log"
    log_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"LIGGGHTS failed with code {proc.returncode}; see {log_path}")
    return proc


def parse_last_dump(path: str | Path) -> dict[int, dict[str, float]]:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    headers = [i for i, line in enumerate(lines) if line.startswith("ITEM: ATOMS")]
    if not headers:
        raise ValueError("no ITEM: ATOMS block found in LIGGGHTS dump")
    h = headers[-1]
    columns = lines[h].split()[2:]
    required = {"id", "x", "y", "z", "vx", "vy", "vz"}
    if not required.issubset(columns):
        raise ValueError(f"dump missing required columns: {sorted(required - set(columns))}")
    col = {name: idx for idx, name in enumerate(columns)}
    state = {}
    for line in lines[h + 1:]:
        if line.startswith("ITEM:"):
            break
        if not line.strip():
            continue
        parts = line.split()
        atom_id = int(float(parts[col["id"]]))
        state[atom_id] = {name: float(parts[idx]) for name, idx in col.items() if name != "id"}
    if sorted(state) != list(range(1, N_BALLS + 1)):
        raise ValueError(f"expected IDs 1..25 in final dump, got {sorted(state)}")
    return state


def select_from_state(state: dict[int, dict[str, float]], cfg: LiggghtsConfig) -> list[int]:
    a = math.radians(cfg.outlet_angle_deg)
    u = np.array([math.cos(a), math.sin(a), 0.0])
    scored = []
    for number in range(1, N_BALLS + 1):
        row = state[number]
        p = np.array([row["x"], row["y"], row["z"]])
        v = np.array([row["vx"], row["vy"], row["vz"]])
        score = float(p @ u + cfg.outlet_velocity_weight * (v @ u))
        scored.append((score, number))
    selected = sorted(number for _, number in sorted(scored, reverse=True)[:N_DRAW])
    if len(selected) != N_DRAW or len(set(selected)) != N_DRAW:
        raise AssertionError("selection must contain exactly 14 unique numbers")
    return selected


def perturb_config(cfg: LiggghtsConfig, p: MonteCarloPerturbation, rng: np.random.Generator) -> LiggghtsConfig:
    return replace(
        cfg,
        ball_radius=cfg.ball_radius * (1 + float(rng.normal(0, p.radius_sigma_frac))),
        ball_density=cfg.ball_density * (1 + float(rng.normal(0, p.density_sigma_frac))),
        restitution=float(np.clip(cfg.restitution + rng.normal(0, p.restitution_sigma), 0, 1)),
        friction=float(max(0.0, cfg.friction + rng.normal(0, p.friction_sigma))),
        angular_velocity=cfg.angular_velocity * (1 + float(rng.normal(0, p.omega_sigma_frac))),
    )


def monte_carlo_liggghts(root, runs, seed, cfg, liggghts, timeout=600):
    if runs <= 0:
        raise ValueError("runs must be > 0")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    master = np.random.default_rng(seed)
    perturb = MonteCarloPerturbation()
    counts = np.zeros(N_BALLS, dtype=int)
    selections = []
    for k in range(runs):
        run_seed = int(master.integers(1, 2**31 - 1))
        run_cfg = perturb_config(cfg, perturb, master)
        case = prepare_case(root / f"run_{k:05d}", run_cfg, run_seed)
        run_case(case, liggghts=liggghts, timeout=timeout)
        selected = select_from_state(parse_last_dump(case / "state.dump"), run_cfg)
        counts[np.asarray(selected) - 1] += 1
        selections.append(selected)
    probs = counts / float(runs)
    if not math.isclose(float(probs.sum()), float(N_DRAW), abs_tol=1e-12):
        raise AssertionError(f"sum(P_i) must be 14, got {probs.sum()}")
    result = {
        "backend": "LIGGGHTS-PUBLIC",
        "runs": runs,
        "seed": seed,
        "baseline_probability": N_DRAW / N_BALLS,
        "counts": counts.tolist(),
        "probabilities": probs.tolist(),
        "probability_sum": float(probs.sum()),
        "config": asdict(cfg),
        "perturbation": asdict(perturb),
        "selections": selections,
    }
    (root / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="KinoDEM v2 LIGGGHTS backend")
    ap.add_argument("--workdir", default="kinodem-liggghts-case")
    ap.add_argument("--seed", type=int, default=20260919)
    ap.add_argument("--seconds", type=float, default=0.10)
    ap.add_argument("--dt", type=float, default=1e-5)
    ap.add_argument("--omega", type=float, default=7.0)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--liggghts")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    cfg = LiggghtsConfig(seconds=args.seconds, timestep=args.dt, angular_velocity=args.omega)
    if args.prepare_only:
        print(prepare_case(args.workdir, cfg, args.seed))
        return
    if args.runs == 1:
        case = prepare_case(args.workdir, cfg, args.seed)
        run_case(case, args.liggghts)
        selected = select_from_state(parse_last_dump(case / "state.dump"), cfg)
        (case / "selection.json").write_text(
            json.dumps({"selected": selected, "seed": args.seed, "backend": "LIGGGHTS-PUBLIC"}, indent=2),
            encoding="utf-8",
        )
        print("selected:", " ".join(f"{x:02d}" for x in selected))
    else:
        result = monte_carlo_liggghts(args.workdir, args.runs, args.seed, cfg, args.liggghts)
        order = np.argsort(np.asarray(result["probabilities"]))[::-1]
        print(f"runs={args.runs} sum(P_i)={result['probability_sum']:.12f}")
        for idx in order[:N_DRAW]:
            print(f"{idx+1:02d}: {result['probabilities'][idx]:.6f}")


if __name__ == "__main__":
    main()
