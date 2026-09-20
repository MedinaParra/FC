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

The script builds a background mesh, uses `snappyHexMesh` to retain the air domain inside the globe STL, decomposes to four MPI ranks, and invokes `cfdemSolverIB` through the CFDEM `parCFDDEMrun` helper.

## What is and is not validated

The repository already has real LIGGGHTS executions for the DEM-only globe. This v3 case defines the OpenFOAM/CFDEM side and an explicit two-way MPI contract. Until the coupled solver runtime itself completes successfully, any visualization produced from this case must be labeled as a **model/setup preview**, not as OpenFOAM results.

After a successful coupled run, use the CFD VTK fields plus the LIGGGHTS particle dumps for the numerical-result video.
