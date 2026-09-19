#!/usr/bin/env python3
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from kinofm_v4 import (
    EXPECTED, TimesFM3Scorer, ewma, global_freq, load_sqlite,
    previous, rolling, to_binary, top14
)

def hits_for_scores(scores, actual):
    return int(actual[top14(scores)].sum())

def evaluate_scorer(y, scorer, n_test):
    start = len(y) - n_test
    hits = []
    selections = []
    for t in range(start, len(y)):
        scores = scorer(y[:t])
        selected = top14(scores)
        hits.append(int(y[t, selected].sum()))
        selections.append(" ".join(str(x + 1) for x in selected))
    return np.asarray(hits), selections

def evaluate_baseline(y, scorer, n_test):
    start = len(y) - n_test
    hits = []
    for t in range(start, len(y)):
        selected = top14(scorer(y[:t]))
        hits.append(int(y[t, selected].sum()))
    return np.asarray(hits)

def row(name, mode, hits):
    return {
        "model": name,
        "mode": mode,
        "n_test": int(len(hits)),
        "mean_hits": float(hits.mean()),
        "lift_vs_7_84": float(hits.mean() - EXPECTED),
        "median_hits": float(np.median(hits)),
        "min_hits": int(hits.min()),
        "max_hits": int(hits.max()),
        "pct_10_plus": float(100 * np.mean(hits >= 10)),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--context", type=int, default=128)
    ap.add_argument("--n-test", type=int, default=30)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--seed", type=int, default=20260919)
    ap.add_argument("--outdir", default="ci-results")
    args = ap.parse_args()

    df = load_sqlite(args.sqlite)
    y = to_binary(df)
    rng = np.random.default_rng(args.seed)
    modes = {
        "forward": y,
        "reverse": y[::-1].copy(),
        "shuffled": y[rng.permutation(len(y))],
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    scorer = TimesFM3Scorer(context=args.context, device=args.device)
    rows = []
    details = []

    for mode, data in modes.items():
        hits, selections = evaluate_scorer(data, scorer, args.n_test)
        rows.append(row(f"TimesFM3_ctx{args.context}", mode, hits))
        start = len(data) - args.n_test
        for k, (h, sel) in enumerate(zip(hits, selections)):
            details.append({
                "model": f"TimesFM3_ctx{args.context}",
                "mode": mode,
                "test_index": k,
                "source_index": start + k,
                "hits": int(h),
                "selection": sel,
            })

    baselines = {
        "Previous": previous,
        "GlobalFreq": global_freq,
        "Rolling20": rolling(20),
        "Rolling50": rolling(50),
        "Rolling100": rolling(100),
        "EWMA_002": ewma(0.02),
        "EWMA_005": ewma(0.05),
    }
    for name, base_scorer in baselines.items():
        for mode, data in modes.items():
            hits = evaluate_baseline(data, base_scorer, args.n_test)
            rows.append(row(name, mode, hits))

    summary = pd.DataFrame(rows)
    details_df = pd.DataFrame(details)
    summary.to_csv(outdir / "timesfm30_summary.csv", index=False)
    details_df.to_csv(outdir / "timesfm30_details.csv", index=False)

    print(f"Validated draws: {len(y)} ({df.iloc[0]['sorteo']}..{df.iloc[-1]['sorteo']})")
    print(f"Exact random baseline mean: {EXPECTED:.4f}")
    print(summary.sort_values(["mode", "mean_hits"], ascending=[True, False]).to_string(index=False))

if __name__ == "__main__":
    main()
