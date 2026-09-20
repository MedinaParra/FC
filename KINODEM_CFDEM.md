# KinoDEM CFD-DEM v3 — OpenFOAM + LIGGGHTS

This branch adds a two-way CFD-DEM case for the Kino physical experiment.

## Architecture

```
OpenFOAM-6 / cfdemSolverIB
        ⇅ twoWayMPI
CFDEM coupling
        ⇅ force + particle state
LIGGGHTS
```

The public CFDEM project is specifically designed to couple OpenFOAM and LIGGGHTS. The case uses the immersed-boundary solver pattern from the official `cfdemSolverIB` examples because 25 balls are large relative to the chamber and are intended to be explicitly represented rather than homogenized as a fine granular phase.

## Current model

- Globe-like chamber radius: 0.25 m (surrogate).
- 25 LIGGGHTS spheres, default diameter 0.04 m (surrogate).
- Air: incompressible Newtonian, `nu = 1.5e-5 m2/s`.
- LIGGGHTS DEM timestep: `1e-5 s`.
- CFD timestep: `1e-4 s`.
- Coupling interval: 10 DEM steps per CFD step.
- Coupling: `twoWayMPI`.
- Particle-fluid force models: `ShirgaonkarIB` and `ArchimedesIB`.
- CFD void-fraction model: `IB`.
- Wall hypothesis: the globe rotates around z at 7 rad/s in both solvers.

The rotating wall is a **calibration hypothesis**, not a verified statement about the real Kino machine.

## Generate

```bash
python kinodem_cfdem_case.py --out kinodem-cfdem-case
```

## Run in a CFDEM/OpenFOAM-6 environment

```bash
cd kinodem-cfdem-case
chmod +x Allrun.sh
./Allrun.sh
```

The script builds a background mesh, uses `snappyHexMesh` to retain the air domain inside the globe STL, decomposes to four MPI ranks, and launches `cfdemSolverIB -parallel` directly with MPI. The solver then starts the embedded LIGGGHTS-PFM instance through `twoWayMPI`.

## Verified coupled runtime

A real coupled OpenFOAM/CFDEM/LIGGGHTS-PFM run completed successfully in GitHub Actions on 2026-09-20.

- Workflow run: `35480524521`
- Branch: `kinodem-cfdem-v3`
- Tested commit: `00a8fc27b02661852732970b6c9c70e379ffd997`
- Physical simulated time: `0.02 s`
- DEM steps: `2000`
- Coupling interval: `10`
- OpenFOAM: version 6
- CFD solver: `cfdemSolverIB`
- Data exchange: `twoWayMPI`
- DEM runtime: LIGGGHTS-PFM 21.11
- MPI ranks: 4
- CFD mesh: 5888 cells before VTK decomposition
- `checkMesh`: `Mesh OK`
- Maximum mesh non-orthogonality: `39.890933`
- Maximum skewness: `0.62360778`
- Final cumulative continuity error: approximately `-1.56e-18`
- Solver execution time in CI: `28.82 s`

The coupled run produced OpenFOAM fields including `U`, `p`, `voidfractionNext`, `interFace`, `phiIB`, particle-force fields, and LIGGGHTS particle trajectories. The final VTK point velocity magnitude reached about `1.744 m/s`, consistent with the imposed rotating-wall surrogate near the chamber boundary.

## What is still uncalibrated

Successful numerical execution does **not** make this a validated model of the real Kino machine. The chamber radius, ball diameter/density, contact properties, rotation/agitation law and extraction mechanism are still surrogate or hypothesized parameters. The rotating wall at `7 rad/s` is specifically a calibration hypothesis.

The numerical-result video may therefore be described as a **real CFD-DEM solver result for the surrogate KinoDEM model**, but not as a prediction or validated reconstruction of an actual Kino draw.
