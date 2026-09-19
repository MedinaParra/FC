#!/usr/bin/env python3
"""Bias report for KinoDEM LIGGGHTS Monte Carlo summaries."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

N_BALLS = 25
N_DRAW = 14
P0 = N_DRAW / N_BALLS


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    phat = k / n
    den = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / den
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / den
    return max(0.0, center - half), min(1.0, center + half)


def z_score(k: int, n: int, p0: float = P0) -> float:
    if n <= 0:
        raise ValueError("n must be positive")
    return (k - n * p0) / math.sqrt(n * p0 * (1 - p0))


def normal_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def build_report(summary: dict) -> list[dict]:
    runs = int(summary["runs"])
    counts = [int(x) for x in summary["counts"]]
    if len(counts) != N_BALLS:
        raise ValueError("expected 25 counts")
    if sum(counts) != runs * N_DRAW:
        raise ValueError("count total must equal runs*14")
    rows = []
    for i, k in enumerate(counts, start=1):
        p = k / runs
        lo, hi = wilson_interval(k, runs)
        z = z_score(k, runs)
        pval = normal_two_sided_p(z)
        rows.append({
            "number": i,
            "count": k,
            "runs": runs,
            "p_hat": p,
            "baseline": P0,
            "delta": p - P0,
            "z": z,
            "p_raw_normal": pval,
            "p_bonferroni_25": min(1.0, pval * 25),
            "wilson95_lo": lo,
            "wilson95_hi": hi,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary")
    ap.add_argument("--out", default="kinodem_bias_report.csv")
    args = ap.parse_args()
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    rows = build_report(summary)
    with Path(args.out).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in sorted(rows, key=lambda x: abs(x["z"]), reverse=True):
        print(
            f"{r['number']:02d} p={r['p_hat']:.6f} delta={r['delta']:+.6f} "
            f"z={r['z']:+.3f} pBonf={r['p_bonferroni_25']:.4g}"
        )


if __name__ == "__main__":
    main()
