#!/usr/bin/env python3
import argparse
from pathlib import Path
import math
import numpy as np
import pandas as pd

from kinofm_v4 import EXPECTED, TimesFM3Scorer, ewma, global_freq, load_sqlite, previous, rolling, to_binary, top14

def comb(n,k):
    return math.comb(n,k)

# Hypergeom overlap distribution for two independent 14-subsets of 25.
P_HIT = {k: comb(14,k)*comb(11,14-k)/comb(25,14) for k in range(3,15)}

def exact_upper_tail_sum(total_hits, n):
    # convolution DP of exact null distribution
    dist = np.array([1.0])
    for _ in range(n):
        nd = np.zeros(len(dist)+14)
        for i,p0 in enumerate(dist):
            if p0 == 0: continue
            for k,pk in P_HIT.items():
                nd[i+k] += p0*pk
        dist = nd
    return float(dist[total_hits:].sum())

def bootstrap_ci(hits, seed=20260919, reps=10000):
    rng = np.random.default_rng(seed)
    a = np.asarray(hits, dtype=float)
    idx = rng.integers(0, len(a), size=(reps, len(a)))
    means = a[idx].mean(axis=1)
    return float(np.quantile(means, .025)), float(np.quantile(means, .975))

def summarize(model, mode, context, hits):
    a=np.asarray(hits, dtype=int)
    lo,hi=bootstrap_ci(a, seed=20260919 + (context or 0) + len(model) + len(mode))
    total=int(a.sum())
    return {
        "model":model,
        "mode":mode,
        "context":context,
        "n_test":len(a),
        "mean_hits":float(a.mean()),
        "lift_vs_7_84":float(a.mean()-EXPECTED),
        "ci95_low":lo,
        "ci95_high":hi,
        "exact_p_upper_vs_random":exact_upper_tail_sum(total, len(a)),
        "median_hits":float(np.median(a)),
        "min_hits":int(a.min()),
        "max_hits":int(a.max()),
        "pct_10_plus":float(100*np.mean(a>=10)),
        "total_hits":total,
    }

def baseline_hits(data, scorer, n_test):
    out=[]
    start=len(data)-n_test
    for t in range(start,len(data)):
        sel=top14(scorer(data[:t]))
        out.append(int(data[t,sel].sum()))
    return out

def timesfm_batch_hits(model, data, context, n_test, batch_size=16):
    start=len(data)-n_test
    contexts=[]
    actual=[]
    for t in range(start,len(data)):
        x=data[max(0,t-context):t].T.astype(np.float32)
        contexts.append(x)
        actual.append(data[t])
    hits=[]
    selections=[]
    for i in range(0,len(contexts),batch_size):
        batch=contexts[i:i+batch_size]
        outs=list(model.predict_batch(
            contexts=batch,
            horizon=1,
            return_quantiles=False,
            use_symmetric_averaging=False,
        ))
        for out, y in zip(outs, actual[i:i+batch_size]):
            scores=np.asarray(out.forecast)[:,0]
            sel=top14(scores)
            hits.append(int(y[sel].sum()))
            selections.append(" ".join(str(x+1) for x in sel))
    return hits,selections

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sqlite",required=True)
    ap.add_argument("--n-test",type=int,default=100)
    ap.add_argument("--contexts",default="64,128,256,512")
    ap.add_argument("--device",default="cpu")
    ap.add_argument("--seed",type=int,default=20260919)
    ap.add_argument("--batch-size",type=int,default=16)
    ap.add_argument("--outdir",default="matrix-results")
    args=ap.parse_args()

    contexts=[int(x) for x in args.contexts.split(",") if x.strip()]
    df=load_sqlite(args.sqlite)
    y=to_binary(df)
    rng=np.random.default_rng(args.seed)
    modes={
        "forward":y,
        "reverse":y[::-1].copy(),
        "shuffled":y[rng.permutation(len(y))]
    }

    outdir=Path(args.outdir); outdir.mkdir(parents=True,exist_ok=True)
    scorer=TimesFM3Scorer(context=max(contexts),device=args.device)
    model=scorer.model

    summary=[]
    details=[]

    # Baselines once per mode.
    baselines={
        "Previous":previous,
        "GlobalFreq":global_freq,
        "Rolling20":rolling(20),
        "Rolling50":rolling(50),
        "Rolling100":rolling(100),
        "EWMA_002":ewma(.02),
        "EWMA_005":ewma(.05),
    }
    for mode,data in modes.items():
        for name,fn in baselines.items():
            h=baseline_hits(data,fn,args.n_test)
            summary.append(summarize(name,mode,None,h))

    # TimesFM matrix.
    for context in contexts:
        for mode,data in modes.items():
            h,sels=timesfm_batch_hits(model,data,context,args.n_test,args.batch_size)
            summary.append(summarize("TimesFM3",mode,context,h))
            start=len(data)-args.n_test
            for k,(hit,sel) in enumerate(zip(h,sels)):
                details.append({
                    "model":"TimesFM3","mode":mode,"context":context,
                    "test_index":k,"source_index":start+k,
                    "hits":hit,"selection":sel
                })

    sdf=pd.DataFrame(summary)
    ddf=pd.DataFrame(details)
    sdf.to_csv(outdir/"matrix_summary.csv",index=False)
    ddf.to_csv(outdir/"matrix_details.csv",index=False)

    # Context comparison focused on TimesFM.
    tf=sdf[sdf.model=="TimesFM3"].copy()
    piv=tf.pivot(index="context",columns="mode",values="mean_hits").reset_index()
    piv["forward_minus_reverse"]=piv["forward"]-piv["reverse"]
    piv["forward_minus_shuffled"]=piv["forward"]-piv["shuffled"]
    piv.to_csv(outdir/"timesfm_context_comparison.csv",index=False)

    print(f"Validated draws: {len(y)} ({df.iloc[0]['sorteo']}..{df.iloc[-1]['sorteo']})")
    print(f"Exact random mean baseline: {EXPECTED:.4f}")
    print("\nTIMESFM MATRIX")
    print(tf.sort_values(["context","mode"]).to_string(index=False))
    print("\nCONTEXT COMPARISON")
    print(piv.to_string(index=False))
    print("\nFORWARD BASELINES")
    print(sdf[(sdf.model!="TimesFM3") & (sdf.mode=="forward")].sort_values("mean_hits",ascending=False).to_string(index=False))

if __name__=="__main__":
    main()
