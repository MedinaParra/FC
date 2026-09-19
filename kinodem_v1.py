#!/usr/bin/env python3
"""
KinoDEM v1
==========

Discrete-element-inspired physical simulator for 25 Kino balls.

Scope:
- 2D circular rotating drum;
- rigid spherical/disc particles with impulse-based collisions;
- ball-ball restitution and Coulomb-like tangential friction;
- moving-wall collision against a rotating drum;
- gravity and linear air drag;
- deterministic seeded initial conditions;
- Monte Carlo perturbation of initial states and physical parameters;
- outputs inclusion probabilities for a 14-of-25 draw.

This is an *uncalibrated physical surrogate*, not a claim that the real Kino
machine can be predicted from historical results. Calibration requires measured
machine geometry, ball properties, drum speed and pre-draw state (e.g. video).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

import numpy as np

N_BALLS = 25
N_DRAW = 14


@dataclass(frozen=True)
class BallSpec:
    number: int
    radius: float = 0.020
    mass: float = 0.004
    restitution: float = 0.82
    friction: float = 0.18


@dataclass(frozen=True)
class DrumConfig:
    radius: float = 0.25
    angular_velocity: float = 7.0
    gravity: float = 9.81
    air_drag: float = 0.08
    dt: float = 0.003
    mix_seconds: float = 1.2
    outlet_angle_deg: float = 90.0
    outlet_velocity_weight: float = 0.035
    solver_passes: int = 2


@dataclass(frozen=True)
class PerturbationConfig:
    radius_sigma_frac: float = 0.0025
    mass_sigma_frac: float = 0.005
    restitution_sigma: float = 0.01
    friction_sigma: float = 0.01
    drum_omega_sigma_frac: float = 0.01


def default_balls() -> list[BallSpec]:
    return [BallSpec(i) for i in range(1, N_BALLS + 1)]


def _tangent(v: np.ndarray) -> np.ndarray:
    return np.array([-v[1], v[0]], dtype=float)


class KinoDEMSimulator:
    def __init__(
        self,
        balls: Iterable[BallSpec] | None = None,
        drum: DrumConfig | None = None,
    ):
        self.balls = list(default_balls() if balls is None else balls)
        self.drum = drum or DrumConfig()
        if len(self.balls) != N_BALLS:
            raise ValueError(f"KinoDEM requires exactly {N_BALLS} balls")
        numbers = [b.number for b in self.balls]
        if sorted(numbers) != list(range(1, N_BALLS + 1)):
            raise ValueError("Ball numbers must be exactly 1..25")
        if any(b.radius <= 0 or b.mass <= 0 for b in self.balls):
            raise ValueError("Ball radius and mass must be positive")
        max_r = max(b.radius for b in self.balls)
        if self.drum.radius <= 3.0 * max_r:
            raise ValueError("Drum radius is too small for the configured balls")
        if self.drum.dt <= 0 or self.drum.mix_seconds <= 0:
            raise ValueError("dt and mix_seconds must be positive")
        if self.drum.solver_passes < 1:
            raise ValueError("solver_passes must be >= 1")

        self.radii = np.array([b.radius for b in self.balls], dtype=float)
        self.masses = np.array([b.mass for b in self.balls], dtype=float)
        self.restitution = np.array([b.restitution for b in self.balls], dtype=float)
        self.friction = np.array([b.friction for b in self.balls], dtype=float)

    def initialize(self, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        pos = np.zeros((N_BALLS, 2), dtype=float)
        vel = np.zeros((N_BALLS, 2), dtype=float)

        for i in range(N_BALLS):
            limit = self.drum.radius - self.radii[i] - 1e-6
            placed = False
            for _ in range(50_000):
                rho = limit * math.sqrt(float(rng.random()))
                theta = float(rng.uniform(0, 2 * math.pi))
                candidate = rho * np.array([math.cos(theta), math.sin(theta)])
                if i == 0:
                    ok = True
                else:
                    d = np.linalg.norm(pos[:i] - candidate, axis=1)
                    ok = bool(np.all(d > (self.radii[:i] + self.radii[i] + 2e-4)))
                if ok:
                    pos[i] = candidate
                    placed = True
                    break
            if not placed:
                raise RuntimeError("Could not place all balls without overlap")

        vel[:] = rng.normal(0.0, 0.15, size=(N_BALLS, 2))
        return pos, vel

    def _resolve_wall(self, pos: np.ndarray, vel: np.ndarray) -> None:
        for i in range(N_BALLS):
            dist = float(np.linalg.norm(pos[i]))
            allowed = self.drum.radius - self.radii[i]
            if dist <= allowed:
                continue
            if dist < 1e-12:
                n = np.array([1.0, 0.0])
            else:
                n = pos[i] / dist

            pos[i] = n * allowed
            wall_v = self.drum.angular_velocity * _tangent(pos[i])
            rel = vel[i] - wall_v
            vn = float(np.dot(rel, n))
            if vn > 0.0:
                rel = rel - (1.0 + self.restitution[i]) * vn * n

            vt_vec = rel - float(np.dot(rel, n)) * n
            vt = float(np.linalg.norm(vt_vec))
            if vt > 0:
                max_reduce = self.friction[i] * abs(vn) * (1.0 + self.restitution[i])
                reduce = min(vt, max_reduce)
                rel -= (reduce / vt) * vt_vec

            vel[i] = wall_v + rel

    def _resolve_pairs(self, pos: np.ndarray, vel: np.ndarray) -> None:
        for i in range(N_BALLS - 1):
            for j in range(i + 1, N_BALLS):
                delta = pos[i] - pos[j]
                dist2 = float(np.dot(delta, delta))
                min_dist = self.radii[i] + self.radii[j]
                if dist2 >= min_dist * min_dist:
                    continue

                dist = math.sqrt(max(dist2, 1e-18))
                if dist < 1e-9:
                    a = (i * 0.754877666 + j * 0.569840296) % 1.0 * 2 * math.pi
                    n = np.array([math.cos(a), math.sin(a)])
                else:
                    n = delta / dist

                inv_i = 1.0 / self.masses[i]
                inv_j = 1.0 / self.masses[j]
                inv_sum = inv_i + inv_j

                overlap = min_dist - dist
                correction = overlap / inv_sum
                pos[i] += correction * inv_i * n
                pos[j] -= correction * inv_j * n

                rv = vel[i] - vel[j]
                vn = float(np.dot(rv, n))
                if vn >= 0.0:
                    continue

                e = min(self.restitution[i], self.restitution[j])
                jn = -(1.0 + e) * vn / inv_sum
                impulse_n = jn * n
                vel[i] += inv_i * impulse_n
                vel[j] -= inv_j * impulse_n

                rv2 = vel[i] - vel[j]
                vt_vec = rv2 - float(np.dot(rv2, n)) * n
                vt = float(np.linalg.norm(vt_vec))
                if vt > 1e-12:
                    t = vt_vec / vt
                    jt_uncapped = -vt / inv_sum
                    mu = math.sqrt(self.friction[i] * self.friction[j])
                    jt = float(np.clip(jt_uncapped, -mu * jn, mu * jn))
                    impulse_t = jt * t
                    vel[i] += inv_i * impulse_t
                    vel[j] -= inv_j * impulse_t

    def step(self, pos: np.ndarray, vel: np.ndarray) -> None:
        dt = self.drum.dt
        vel[:, 1] -= self.drum.gravity * dt
        vel *= math.exp(-self.drum.air_drag * dt)
        pos += vel * dt

        for _ in range(self.drum.solver_passes):
            self._resolve_pairs(pos, vel)
            self._resolve_wall(pos, vel)

        if not np.isfinite(pos).all() or not np.isfinite(vel).all():
            raise FloatingPointError("Non-finite state produced by simulation")

    def mix(self, pos: np.ndarray, vel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        steps = max(1, int(round(self.drum.mix_seconds / self.drum.dt)))
        for _ in range(steps):
            self.step(pos, vel)
        return pos, vel

    def selection_scores(self, pos: np.ndarray, vel: np.ndarray) -> np.ndarray:
        a = math.radians(self.drum.outlet_angle_deg)
        u = np.array([math.cos(a), math.sin(a)])
        radial_projection = pos @ u
        velocity_projection = vel @ u
        return radial_projection + self.drum.outlet_velocity_weight * velocity_projection

    def run(self, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = np.random.default_rng(seed)
        pos, vel = self.initialize(rng)
        self.mix(pos, vel)
        scores = self.selection_scores(pos, vel)
        selected_idx = np.argsort(scores, kind="stable")[-N_DRAW:]
        selected_numbers = np.sort(selected_idx + 1)
        return selected_numbers, pos.copy(), vel.copy()


def perturb_system(
    base_balls: list[BallSpec],
    base_drum: DrumConfig,
    perturb: PerturbationConfig,
    rng: np.random.Generator,
) -> tuple[list[BallSpec], DrumConfig]:
    balls: list[BallSpec] = []
    for b in base_balls:
        radius = b.radius * (1.0 + float(rng.normal(0, perturb.radius_sigma_frac)))
        mass = b.mass * (1.0 + float(rng.normal(0, perturb.mass_sigma_frac)))
        restitution = float(np.clip(
            b.restitution + rng.normal(0, perturb.restitution_sigma), 0.0, 1.0
        ))
        friction = float(max(0.0, b.friction + rng.normal(0, perturb.friction_sigma)))
        balls.append(replace(
            b, radius=radius, mass=mass, restitution=restitution, friction=friction
        ))

    omega = base_drum.angular_velocity * (
        1.0 + float(rng.normal(0, perturb.drum_omega_sigma_frac))
    )
    drum = replace(base_drum, angular_velocity=omega)
    return balls, drum


def monte_carlo(
    runs: int,
    seed: int = 20260919,
    balls: list[BallSpec] | None = None,
    drum: DrumConfig | None = None,
    perturb: PerturbationConfig | None = None,
) -> dict:
    if runs <= 0:
        raise ValueError("runs must be > 0")

    base_balls = list(default_balls() if balls is None else balls)
    base_drum = drum or DrumConfig()
    perturb = perturb or PerturbationConfig()
    master = np.random.default_rng(seed)

    counts = np.zeros(N_BALLS, dtype=np.int64)
    draws: list[list[int]] = []

    for _ in range(runs):
        physical_seed = int(master.integers(0, 2**63 - 1))
        param_seed = int(master.integers(0, 2**63 - 1))
        prng = np.random.default_rng(param_seed)
        run_balls, run_drum = perturb_system(base_balls, base_drum, perturb, prng)
        sim = KinoDEMSimulator(run_balls, run_drum)
        selected, _, _ = sim.run(physical_seed)
        counts[selected - 1] += 1
        draws.append(selected.tolist())

    probs = counts / float(runs)
    expected_sum = float(N_DRAW)
    if not math.isclose(float(probs.sum()), expected_sum, rel_tol=0, abs_tol=1e-12):
        raise AssertionError(
            f"Inclusion probabilities must sum to {expected_sum}, got {probs.sum()}"
        )

    return {
        "runs": runs,
        "seed": seed,
        "baseline_inclusion_probability": N_DRAW / N_BALLS,
        "counts": counts.tolist(),
        "probabilities": probs.tolist(),
        "draws": draws,
        "probability_sum": float(probs.sum()),
        "drum": asdict(base_drum),
        "perturbation": asdict(perturb),
    }


def write_outputs(result: dict, outdir: str | Path) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / "kinodem_probabilities.csv"
    baseline = float(result["baseline_inclusion_probability"])
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["number", "count", "probability", "baseline", "delta_vs_baseline"])
        for i, (c, p) in enumerate(zip(result["counts"], result["probabilities"]), start=1):
            w.writerow([i, c, f"{p:.12f}", f"{baseline:.12f}", f"{p-baseline:.12f}"])

    summary = {k: v for k, v in result.items() if k != "draws"}
    (outdir / "kinodem_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="KinoDEM v1 2D physical Monte Carlo surrogate")
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260919)
    ap.add_argument("--mix-seconds", type=float, default=1.2)
    ap.add_argument("--dt", type=float, default=0.003)
    ap.add_argument("--omega", type=float, default=7.0)
    ap.add_argument("--outlet-angle", type=float, default=90.0)
    ap.add_argument("--outdir", default="kinodem-results")
    args = ap.parse_args()

    drum = DrumConfig(
        angular_velocity=args.omega,
        dt=args.dt,
        mix_seconds=args.mix_seconds,
        outlet_angle_deg=args.outlet_angle,
    )
    result = monte_carlo(args.runs, args.seed, drum=drum)
    write_outputs(result, args.outdir)

    probs = np.asarray(result["probabilities"])
    order = np.argsort(probs)[::-1]
    print("KinoDEM v1 — uncalibrated 2D physical surrogate")
    print(f"runs={result['runs']} seed={result['seed']} P0={N_DRAW/N_BALLS:.6f}")
    print(f"sum(P_i)={probs.sum():.12f} (must equal {N_DRAW})")
    print("Top inclusion probabilities (simulation only):")
    for idx in order[:N_DRAW]:
        print(f"{idx+1:02d}: {probs[idx]:.6f}")


if __name__ == "__main__":
    main()
