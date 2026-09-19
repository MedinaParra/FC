#!/usr/bin/env python3
"""
KinoFM v4
=========
Auditoría reproducible de señal temporal para Kino Chile (14 de 25).

Incluye:
- lectura desde CSV o SQLite histórico;
- reparación opcional de dos errores conocidos de transcripción (#2247 y #2256);
- validación 14/25;
- baseline matemático;
- walk-forward causal;
- Markov propio (cada número depende de su estado anterior);
- Markov cruzado 25x25;
- forward / reverse;
- auditoría de transiciones y corrección Bonferroni;
- adaptador TimesFM 3.0 opcional;
- modo shuffled para comprobar si el modelo explota tiempo real o ruido.

No interpreta los scores de TimesFM como probabilidades.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path
from typing import Callable, Dict, Tuple

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

N = 25
K = 14
EXPECTED = K * K / N  # 7.84


def validate_numbers(nums):
    nums = [int(x) for x in nums]
    if len(nums) != 14:
        raise ValueError(f"Se esperaban 14 números, llegaron {len(nums)}")
    if len(set(nums)) != 14:
        raise ValueError(f"Números repetidos: {nums}")
    if not all(1 <= x <= 25 for x in nums):
        raise ValueError(f"Números fuera de 1..25: {nums}")
    return sorted(nums)


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = [f"n{i}" for i in range(1, 15)]
    req = {"sorteo", "fecha", *cols}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas: {sorted(missing)}")
    rows = []
    for _, r in df.iterrows():
        nums = validate_numbers([r[c] for c in cols])
        rows.append([int(r["sorteo"]), str(r["fecha"]), *nums])
    return pd.DataFrame(rows, columns=["sorteo", "fecha", *cols]).sort_values("sorteo")


def load_sqlite(path: str, repair_known: bool = True) -> pd.DataFrame:
    con = sqlite3.connect(path)
    try:
        df = pd.read_sql_query(
            """
            SELECT nrosorteo AS sorteo, fecha, tiposorteo,
                   n01,n02,n03,n04,n05,n06,n07,
                   n08,n09,n10,n11,n12,n13,n14
            FROM sorteos
            WHERE tiposorteo='Kino'
            ORDER BY CAST(nrosorteo AS INTEGER)
            """,
            con,
        )
    finally:
        con.close()

    cols = [f"n{i:02d}" for i in range(1, 15)]

    if repair_known:
        fixes = {
            2247: [2,5,6,7,8,12,13,16,17,18,19,22,24,25],
            2256: [2,3,6,7,8,10,12,13,17,19,21,22,23,24],
        }
        for sorteo, nums in fixes.items():
            mask = pd.to_numeric(df["sorteo"], errors="coerce") == sorteo
            if mask.any():
                df.loc[mask, cols] = nums

    rows = []
    for _, r in df.iterrows():
        nums = validate_numbers([r[c] for c in cols])
        rows.append([int(r["sorteo"]), str(r["fecha"]), *nums])

    outcols = ["sorteo", "fecha"] + [f"n{i}" for i in range(1, 15)]
    return pd.DataFrame(rows, columns=outcols).sort_values("sorteo").reset_index(drop=True)


def to_binary(df: pd.DataFrame) -> np.ndarray:
    cols = [f"n{i}" for i in range(1, 15)]
    y = np.zeros((len(df), N), dtype=np.int8)
    for i, r in df.reset_index(drop=True).iterrows():
        nums = np.array([int(r[c]) for c in cols])
        y[i, nums - 1] = 1
    if not np.all(y.sum(axis=1) == 14):
        raise AssertionError("Hay filas binarias que no suman 14")
    return y


def top14(scores):
    return np.sort(np.argsort(np.asarray(scores), kind="stable")[-14:])


def previous(history):
    return history[-1].astype(float)


def global_freq(history):
    return history.mean(axis=0)


def rolling(window):
    return lambda h: h[-min(window, len(h)):].mean(axis=0)


def ewma(alpha):
    def scorer(h):
        s = h[0].astype(float).copy()
        for row in h[1:]:
            s = alpha * row + (1 - alpha) * s
        return s
    return scorer


def self_markov(history, alpha=1.0):
    if len(history) < 2:
        return np.full(N, K / N)
    c11 = np.full(N, alpha); c10 = np.full(N, alpha)
    c01 = np.full(N, alpha); c00 = np.full(N, alpha)
    for a, b in zip(history[:-1], history[1:]):
        c11 += (a == 1) & (b == 1)
        c10 += (a == 1) & (b == 0)
        c01 += (a == 0) & (b == 1)
        c00 += (a == 0) & (b == 0)
    p11 = c11 / (c11 + c10)
    p01 = c01 / (c01 + c00)
    return np.where(history[-1] == 1, p11, p01)


def cross_markov(history, alpha=2.0):
    if len(history) < 2:
        return np.full(N, K / N)
    transitions = len(history) - 1
    pair = np.full((N, N), alpha, dtype=float)
    current_count = np.full(N, 2 * alpha, dtype=float)
    next_count = np.full(N, alpha, dtype=float)
    for cur, nxt in zip(history[:-1], history[1:]):
        next_count += nxt
        active = np.flatnonzero(cur)
        current_count[active] += 1
        for i in active:
            pair[i] += nxt
    base = next_count / (transitions + 2 * alpha)
    active_now = np.flatnonzero(history[-1])
    scores = base.copy()
    for j in range(N):
        lifts = [pair[i, j] / current_count[i] - base[j] for i in active_now]
        scores[j] += np.mean(lifts)
    return scores


def walk_forward(y, scorer: Callable, start=512):
    hit = []
    for t in range(start, len(y)):
        sel = top14(scorer(y[:t]))
        hit.append(int(y[t, sel].sum()))
    a = np.asarray(hit)
    return {
        "n": len(a),
        "mean_hits": float(a.mean()),
        "lift_vs_7_84": float(a.mean() - EXPECTED),
        "pct_10_plus": float(100 * np.mean(a >= 10)),
        "max_hits": int(a.max()),
    }


def transition_audit(y):
    rows = []
    for i in range(N):
        cur = y[:-1, i]
        for j in range(N):
            nxt = y[1:, j]
            a = int(np.sum((cur == 1) & (nxt == 1)))
            b = int(np.sum((cur == 1) & (nxt == 0)))
            c = int(np.sum((cur == 0) & (nxt == 1)))
            d = int(np.sum((cur == 0) & (nxt == 0)))
            p1 = a / (a + b); p0 = c / (c + d)
            _, p = fisher_exact([[a, b], [c, d]], alternative="two-sided")
            rows.append({"from": i + 1, "to": j + 1, "p_next_if_present": p1,
                         "p_next_if_absent": p0, "difference": p1 - p0,
                         "p_raw": p, "p_bonferroni_625": min(1.0, p * 625)})
    return pd.DataFrame(rows).sort_values("p_raw")


class TimesFM3Scorer:
    def __init__(self, context=512, device="cuda"):
        try:
            from timesfm3 import TimesFM3Evaluator, ModelConfig
        except Exception as exc:
            raise RuntimeError('TimesFM 3.0 no está instalado') from exc
        self.context = context
        self.model = TimesFM3Evaluator(ModelConfig(
            checkpoint_path="google/timesfm-3.0-pytorch",
            per_core_batch_size=16,
            device=device,
        ))

    def __call__(self, history):
        x = history[-min(self.context, len(history)):].T.astype(np.float32)
        out = list(self.model.predict_batch(
            contexts=[x], horizon=1, return_quantiles=False,
            use_symmetric_averaging=False,
        ))[0]
        scores = np.asarray(out.forecast)[:, 0]
        if scores.shape != (25,):
            raise RuntimeError(f"Salida TimesFM inesperada: {np.asarray(out.forecast).shape}")
        return scores


def shuffled_copy(y, seed):
    rng = np.random.default_rng(seed)
    return y[rng.permutation(len(y))]


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv"); src.add_argument("--sqlite")
    ap.add_argument("--start", type=int, default=512)
    ap.add_argument("--outdir", default="kinofm_v4_results")
    ap.add_argument("--timesfm", action="store_true")
    ap.add_argument("--context", type=int, default=512)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--shuffle-seed", type=int, default=20260919)
    args = ap.parse_args()
    df = load_csv(args.csv) if args.csv else load_sqlite(args.sqlite)
    y = to_binary(df)
    if args.start >= len(y):
        raise ValueError(f"--start={args.start} >= n={len(y)}")
    models: Dict[str, Callable] = {
        "Previous": previous, "GlobalFreq": global_freq,
        "Rolling20": rolling(20), "Rolling50": rolling(50),
        "Rolling100": rolling(100), "EWMA_002": ewma(0.02),
        "EWMA_005": ewma(0.05), "SelfMarkov": self_markov,
        "CrossMarkov": cross_markov,
    }
    if args.timesfm:
        models[f"TimesFM3_ctx{args.context}"] = TimesFM3Scorer(args.context, args.device)
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    rows = []; reverse = y[::-1].copy(); shuffled = shuffled_copy(y, args.shuffle_seed)
    for name, scorer in models.items():
        fwd = walk_forward(y, scorer, args.start)
        rev = walk_forward(reverse, scorer, args.start)
        shf = walk_forward(shuffled, scorer, args.start)
        rows.append({"model": name, "forward_mean": fwd["mean_hits"],
                     "reverse_mean": rev["mean_hits"], "shuffled_mean": shf["mean_hits"],
                     "forward_lift": fwd["lift_vs_7_84"],
                     "forward_minus_reverse": fwd["mean_hits"] - rev["mean_hits"],
                     "forward_minus_shuffled": fwd["mean_hits"] - shf["mean_hits"],
                     "n_test": fwd["n"]})
    summary = pd.DataFrame(rows).sort_values("forward_mean", ascending=False)
    summary.to_csv(outdir / "forward_reverse_shuffled.csv", index=False)
    trans = transition_audit(y); trans.to_csv(outdir / "transition_audit_625.csv", index=False)
    print(f"Sorteos: {len(y)} | baseline exacto: {EXPECTED:.4f}")
    print("\nFORWARD / REVERSE / SHUFFLED"); print(summary.to_string(index=False))
    print("\nTOP 15 TRANSICIONES POR p BRUTO"); print(trans.head(15).to_string(index=False))
    sig = int((trans["p_bonferroni_625"] < 0.05).sum()); raw = int((trans["p_raw"] < 0.05).sum())
    print(f"\n625 pruebas: p bruto<0.05 = {raw}; Bonferroni<0.05 = {sig}")
    print("Por azar se esperan ~31.25 p-valores < 0.05 entre 625 pruebas.")

if __name__ == "__main__":
    main()
