#!/usr/bin/env python3
import argparse
import numpy as np
from kinofm_v4 import load_sqlite, to_binary, TimesFM3Scorer, top14


def hit_count(selected, actual):
    return int(actual[selected].sum())


def one_case(name, y, scorer):
    history = y[:-1]
    actual = y[-1]
    scores = scorer(history)
    selected = top14(scores)
    hits = hit_count(selected, actual)
    print(f"{name}: hits={hits}; selected={' '.join(str(x+1) for x in selected)}")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sqlite', required=True)
    ap.add_argument('--context', type=int, default=128)
    ap.add_argument('--device', default='cpu')
    ap.add_argument('--seed', type=int, default=20260919)
    args = ap.parse_args()
    df = load_sqlite(args.sqlite)
    y = to_binary(df)
    print(f"Loaded {len(y)} validated Kino draws: {df.iloc[0]['sorteo']}..{df.iloc[-1]['sorteo']}")
    scorer = TimesFM3Scorer(context=args.context, device=args.device)
    rng = np.random.default_rng(args.seed)
    fwd = one_case('forward', y, scorer)
    rev = one_case('reverse', y[::-1].copy(), scorer)
    shf = one_case('shuffled', y[rng.permutation(len(y))], scorer)
    print(f"SMOKE_RESULT forward={fwd} reverse={rev} shuffled={shf}")

if __name__ == '__main__':
    main()
