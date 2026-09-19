# KinoDEM v2 — LIGGGHTS backend

This branch moves the physical experiment from the small Python DEM surrogate to **LIGGGHTS-PUBLIC**.

## Why LIGGGHTS

LIGGGHTS is a discrete-element solver derived from LAMMPS and includes granular contact models, spherical particles, triangular mesh walls, moving/rotating wall surfaces, and parallel execution.

The official public repository states that Aspherix is the successor to LIGGGHTS. KinoDEM nevertheless uses the open LIGGGHTS-PUBLIC-compatible 3.8 solver because it exposes the DEM features required here.

CI runs on Ubuntu 24.04 and installs the distribution's `liggghts` package. The workflow records the exact installed package version as an artifact. The upstream source repository remains `CFDEMproject/LIGGGHTS-PUBLIC` for code/documentation reference.

## Current physical model

- 25 spherical particles; particle ID = Kino number.
- 3D cylindrical drum written as ASCII STL.
- Drum axis: z.
- Gravity: -y.
- Rotating wall surface via `fix mesh/surface ... surface_ang_vel`.
- Hertz normal contact + tangential history.
- `nve/sphere` time integration.
- Dump contains particle ID, position, translational velocity, angular velocity and radius.
- Monte Carlo perturbs radius, density, restitution, friction, drum speed and initial state.

All dimensions/material constants are currently **surrogate values**. Do not interpret the resulting number probabilities as measured probabilities for the real Kino machine.

## Run

Prepare a case without requiring LIGGGHTS:

```bash
python kinodem_liggghts.py --prepare-only --workdir case
```

Run one physical case:

```bash
python kinodem_liggghts.py \
  --workdir case \
  --seconds 0.10 \
  --liggghts /path/to/lmp_serial
```

Run a physical Monte Carlo batch:

```bash
python kinodem_liggghts.py \
  --workdir mc \
  --runs 100 \
  --seconds 0.10 \
  --liggghts /path/to/lmp_serial
```

## Important limitation: extraction

v2 simulates mixing in the closed rotating drum. The current 14-ball extraction is a post-processing outlet score using position and velocity relative to a configurable outlet direction.

That is intentionally separated from DEM. Once the real extraction geometry is known, this scorer should be replaced with an explicit outlet/port mesh and actual particle escape events.

## Calibration targets for v3

1. Real drum radius, depth and internal geometry.
2. Actual agitation/rotation profile versus time.
3. Outlet/port geometry and gate timing.
4. Diameter and mass of every numbered ball.
5. Ball-ball and ball-wall restitution.
6. Static/dynamic/rolling friction.
7. High-speed video reconstruction of initial and pre-extraction states.
8. Airflow; if material, move to CFDEM CFD-DEM coupling.

## Scientific validation

The null model remains symmetric inclusion probability:

```
P0 = 14/25 = 0.56
```

For every Monte Carlo batch selecting exactly 14 balls:

```
sum(P_i) = 14
```

Any claimed physical bias must survive parameter uncertainty, repeated initial-condition perturbation and validation against real machine data from the same hardware configuration.


## Verified physical smoke run

A real LIGGGHTS-PUBLIC executable was compiled from upstream source and executed by GitHub Actions on 2026-09-19:

- workflow run: `35472311678`
- branch: `kinodem-liggghts-v2`
- tested commit: `555bac2b4a6f4e343b30c3070d0b44c05964003d`
- Python generator/parser job: success
- LIGGGHTS build job: success
- physical DEM execution: success
- produced artifact: `kinodem-liggghts-physical-smoke`

The smoke case returned the post-processing selection:

```
02 03 04 05 06 07 11 13 16 17 18 19 22 24
```

This selection is recorded only as a reproducibility check. The model is still uncalibrated and the selection is **not** presented as a prediction of a real Kino draw.


## Globe geometry and per-ball calibration

The default geometry is now `globe`, generated as a closed triangulated UV-sphere because public images of the Kino draw equipment show a globe-like transparent chamber. The previous cylindrical chamber remains available with `--geometry cylinder` for regression tests.

KinoDEM can ingest measured data for every numbered ball:

```csv
number,diameter_m,mass_kg
1,0.000000,0.000000
2,0.000000,0.000000
...
25,0.000000,0.000000
```

The zeroes above are schema placeholders only and are not valid calibration values. A real file must contain positive measured diameter and mass for each number exactly once. Run it with:

```bash
python kinodem_liggghts.py \
  --ball-calibration measured_balls.csv \
  --workdir measured-case \
  --liggghts /usr/bin/liggghts
```

For each particle KinoDEM computes density from the measured mass and diameter and writes the per-particle diameter/density to the LIGGGHTS sphere data.

## Verified globe + Monte Carlo run

GitHub Actions run `35472737645` completed successfully on 2026-09-19 with Ubuntu's LIGGGHTS package version `3.8.0+repack1-9.1build2`.

It verified:

- the globe STL generator;
- non-overlapping 3D initial conditions;
- per-ball mass/diameter calibration parsing;
- a real single-case LIGGGHTS execution;
- eight independent physical LIGGGHTS runs;
- Monte Carlo probability accounting;
- the physical-bias report.

The Monte Carlo smoke batch satisfied the exact accounting invariant:

```
runs = 8
sum(P_i) = 14.0
sum(count_i) = 8 * 14 = 112
```

All Bonferroni-adjusted bias p-values in this tiny smoke batch were 1.0. This is expected and is evidence that the smoke test must not be interpreted as detecting a real ball bias. Its purpose is to verify the end-to-end physical pipeline.
