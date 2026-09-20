#!/usr/bin/env python3
"""
KinoCFDDEM v4.1 - visual geometry calibration.

This module deliberately calibrates only what public imagery supports.
It combines dimensionless globe/ball ratios with explicit uncertainty.
It does NOT infer an absolute ball diameter unless an external dimensional
anchor is supplied.

Usage:
  python kinodem_video_calibration.py \
      calibration/kino_visual_geometry_v4_1.json \
      --out calibration/kino_visual_geometry_v4_1_result.json

Optional:
  --ball-diameter-mm 40
may be used only as a scenario/sensitivity anchor; it is not promoted to a
measured Kino dimension by this program.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def weighted_ratio(observations, systematic_fraction: float):
    rows = [
        x for x in observations
        if x.get("quantitative")
        and x.get("quantity") == "globe_diameter_over_ball_diameter"
    ]
    if not rows:
        raise ValueError("No quantitative globe/ball observations")

    weights = [1.0 / (float(x["sigma"]) ** 2) for x in rows]
    mean = sum(w * float(x["ratio"]) for w, x in zip(weights, rows)) / sum(weights)
    sigma_stat = math.sqrt(1.0 / sum(weights))
    sigma_sys = abs(mean) * float(systematic_fraction)
    sigma_total = math.sqrt(sigma_stat**2 + sigma_sys**2)
    return rows, mean, sigma_stat, sigma_sys, sigma_total


def calibrate(doc, model_ratio=12.5, ball_diameter_mm=None):
    rows, mean, sstat, ssys, stot = weighted_ratio(
        doc["observations"],
        doc.get("systematic_fraction_for_visual_ratio", 0.0),
    )
    z = (float(model_ratio) - mean) / stot
    low95 = mean - 1.96 * stot
    high95 = mean + 1.96 * stot

    result = {
        "n_quantitative_observations": len(rows),
        "globe_to_ball_ratio": {
            "mean": mean,
            "sigma_statistical": sstat,
            "sigma_systematic": ssys,
            "sigma_total": stot,
            "ci95": [low95, high95],
        },
        "existing_model_ratio": float(model_ratio),
        "existing_model_z_from_visual_mean": z,
        "existing_model_inside_visual_95ci": bool(low95 <= model_ratio <= high95),
        "absolute_scale_status": "not_identified",
        "recommended_action": (
            "retain current dimensionless globe/ball ratio for now; "
            "do not claim absolute 500 mm globe or 40 mm ball as measured"
        ),
    }

    if ball_diameter_mm is not None:
        d_ball_m = float(ball_diameter_mm) / 1000.0
        result["scenario_anchor"] = {
            "ball_diameter_mm": float(ball_diameter_mm),
            "status": "user_or_sensitivity_assumption_not_measurement",
            "implied_globe_diameter_m": mean * d_ball_m,
            "implied_globe_diameter_95ci_m": [low95 * d_ball_m, high95 * d_ball_m],
        }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("calibration_json")
    ap.add_argument("--model-ratio", type=float, default=12.5)
    ap.add_argument("--ball-diameter-mm", type=float)
    ap.add_argument("--out")
    args = ap.parse_args()

    src = Path(args.calibration_json)
    doc = json.loads(src.read_text(encoding="utf-8"))
    result = calibrate(doc, args.model_ratio, args.ball_diameter_mm)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
