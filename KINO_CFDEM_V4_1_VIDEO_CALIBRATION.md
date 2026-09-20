# KinoCFDDEM v4.1 — Video Calibrated Geometry

Verified on 2026-09-20.

## Scope
This iteration constrains **dimensionless geometry** from public visual evidence. It does not promote any absolute ball or globe dimension to a measured Kino value unless a dimensional anchor is visible in the same camera plane.

## Verified calibration result
GitHub Actions run: `35533573925` — **success**  
Head commit: `5765d63e6b19e63229360a74ff33116431fe63be`  
Tests: **3 passed**.

- Quantitative visual observations: 2
- Weighted globe diameter / ball diameter: **12.55**
- Statistical sigma: **1.13137**
- Systematic sigma: **1.004**
- Combined sigma: **1.51262**
- 95% interval: **9.5853 to 15.5147**
- Existing surrogate ratio: **12.5**
- Existing-ratio z offset: **-0.0331**
- Existing ratio inside visual 95% interval: **true**
- Absolute scale: **not identified**

## Engineering decision
Retain the current dimensionless globe/ball ratio for the next iteration. Do **not** state that 500 mm globe diameter or 40 mm ball diameter are measured dimensions of the real Kino machine.

The optional 40 mm scenario remains sensitivity-only:
- assumed ball diameter: 40 mm
- implied globe diameter: 0.502 m
- implied 95% range: 0.3834–0.6206 m

## Next measurement
Locate a Lotería de Concepción pre-draw recording with a readable dimensional reference (caliper, micrometer, ruler, or documented ball diameter) in a usable camera plane. Once that anchor is obtained, scale the geometry and re-evaluate CFD/DEM similarity groups and mesh/particle resolution.
