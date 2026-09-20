# KinoCFDDEM v4 — capture-throat instrumentation

v4 builds directly on the numerically validated v3 OpenFOAM/CFDEM/LIGGGHTS surrogate.

## What changes in v4

The principal change is an explicit **virtual capture throat** inside the CFD domain. The purpose is to measure candidate extraction events without allowing particles to leave the OpenFOAM mesh and destabilize the current immersed-boundary coupling.

An event is counted when a numbered ball:

1. crosses from outside to inside the capture zone;
2. fits through the idealized throat using centerline clearance;
3. has velocity directed toward the outlet axis;
4. has not been counted previously.

The first 14 unique events form the v4 capture sequence. If fewer than 14 are observed, the run is reported as incomplete. No numbers are fabricated or padded.

## Why this is not yet a real Kino extraction model

The official Kino rules state that 14 balls are extracted without replacement from 25. v4 implements the **observational uniqueness constraint**, but it does not physically delete a captured ball from the coupled CFD-DEM state. Therefore later events still evolve in the presence of previously observed balls.

This is intentionally recorded as:

```
without_replacement_observation = true
without_replacement_physics = false
```

A future stage should implement a measured outlet mechanism and physical removal/restart sequence after each capture.

## OpenFOAM instrumentation

v4 adds five `probes` near the capture throat and records:

- pressure `p`;
- gas velocity `U`;
- `voidfraction`.

This lets the capture sequence be compared against the local CFD state rather than only against DEM coordinates.

## Generate a v4 case

```bash
python kinocfdem_v4.py generate \
  --out kinocfdem-v4-case \
  --end-time 0.02 \
  --port-radius 0.05 \
  --sensor-depth 0.06
```

## Analyze a LIGGGHTS particle dump

```bash
python kinocfdem_v4.py analyze \
  kinocfdem-v4-case/DEM/post/dump.liggghts_run \
  --outdir extraction-v4
```

Outputs:

- `extraction_events.csv`
- `extraction_summary.json`

## Calibration status

The capture direction, throat radius, throat depth, chamber dimensions, wall agitation law, ball properties and actual extraction mechanism remain parameters to be calibrated from measurements/video. They must not be presented as measured facts unless corresponding evidence is added.
