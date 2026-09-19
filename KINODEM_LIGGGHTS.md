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
