#!/usr/bin/env python3
"""
Evalúa KinoFM sobre la era actual:
- histórico continuo hasta #3280;
- últimos 100 sorteos del histórico como validación forward;
- #3281 como holdout externo final.
"""
import argparse, math
from pathlib import Path

import numpy as np
import pandas as pd

from kinofm_v4 import (
    EXPECTED, TimesFM3Scorer, ewma, global_freq, load_csv, previous,
    rolling, to_binary, top14
)

HOLDOUT_3281 = np.array([5,6,8,9,10,12,13,14,18,20,21,23,24,25], dtype=int)

def comb(n,k): return math.comb(n,k)
P_HIT={k:comb(14,k)*comb(11,14-k)/comb(25,14) for k in range(3,15)}

def exact_upper(total,n):
    dist=np.array([1.0])
    for _ in range(n):
        nd=np.zeros(len(dist)+14)
        for i,p0 in enumerate(dist):
            if p0==0: continue
            for k,pk in P_HIT.items(): nd[i+k]+=p0*pk
        dist=nd
    return float(dist[total:].sum())

def ci95(a):
    a=np.asarray(a,float)
    se=a.std(ddof=1)/np.sqrt(len(a))
    return float(a.mean()-1.96*se), float(a.mean()+1.96*se)

def baseline_hits(y, fn, n_test):
    out=[]
    for t in range(len(y)-n_test,len(y)):
        sel=top14(fn(y[:t]))
        out.append(int(y[t,sel].sum()))
    return out

def timesfm_hits(model, y, context, n_test, batch=16):
    contexts=[]; actual=[]
    for t in range(len(y)-n_test,len(y)):
        contexts.append(y[max(0,t-context):t].T.astype(np.float32))
        actual.append(y[t])
    hits=[]
    for i in range(0,len(contexts),batch):
        outs=list(model.predict_batch(
            contexts=contexts[i:i+batch], horizon=1,
            return_quantiles=False, use_symmetric_averaging=False
        ))
        for out,truth in zip(outs,actual[i:i+batch]):
            score=np.asarray(out.forecast)[:,0]
            sel=top14(score)
            hits.append(int(truth[sel].sum()))
    return hits

def summarize(name, context, hits):
    a=np.asarray(hits,int)
    lo,hi=ci95(a)
    return {
        "model":name,"context":context,"n_test":len(a),
        "mean_hits":float(a.mean()),"lift_vs_7_84":float(a.mean()-EXPECTED),
        "ci95_low":lo,"ci95_high":hi,
        "p_upper_exact_vs_random":exact_upper(int(a.sum()),len(a)),
        "pct_10_plus":float(100*np.mean(a>=10)),
        "min_hits":int(a.min()),"max_hits":int(a.max())
    }

def holdout_baseline(name, fn, y, actual):
    sel=top14(fn(y))
    return {
        "model":name,"context":None,
        "selection":" ".join(str(x+1) for x in sel),
        "hits_3281":int(actual[sel].sum())
    }

def holdout_timesfm(model, y, context, actual):
    x=y[-context:].T.astype(np.float32)
    out=list(model.predict_batch(
        contexts=[x], horizon=1,
        return_quantiles=False, use_symmetric_averaging=False
    ))[0]
    sel=top14(np.asarray(out.forecast)[:,0])
    return {
        "model":"TimesFM3","context":context,
        "selection":" ".join(str(x+1) for x in sel),
        "hits_3281":int(actual[sel].sum())
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv",required=True)
    ap.add_argument("--contexts",default="64,128,256,512")
    ap.add_argument("--n-test",type=int,default=100)
    ap.add_argument("--device",default="cpu")
    ap.add_argument("--outdir",default="current-results")
    args=ap.parse_args()

    contexts=[int(x) for x in args.contexts.split(",")]
    df=load_csv(args.csv)
    y=to_binary(df)
    if int(df.iloc[-1].sorteo)!=3280:
        raise RuntimeError(f"Se esperaba terminar en #3280, termina en {df.iloc[-1].sorteo}")

    actual=np.zeros(25,dtype=np.int8)
    actual[HOLDOUT_3281-1]=1

    outdir=Path(args.outdir); outdir.mkdir(parents=True,exist_ok=True)
    summary=[]; hold=[]

    bases={
        "Previous":previous,
        "GlobalFreq":global_freq,
        "Rolling20":rolling(20),
        "Rolling50":rolling(50),
        "Rolling100":rolling(100),
        "EWMA_002":ewma(.02),
        "EWMA_005":ewma(.05),
    }
    for name,fn in bases.items():
        h=baseline_hits(y,fn,args.n_test)
        summary.append(summarize(name,None,h))
        hold.append(holdout_baseline(name,fn,y,actual))

    scorer=TimesFM3Scorer(context=max(contexts),device=args.device)
    model=scorer.model
    for ctx in contexts:
        h=timesfm_hits(model,y,ctx,args.n_test)
        summary.append(summarize("TimesFM3",ctx,h))
        hold.append(holdout_timesfm(model,y,ctx,actual))

    sdf=pd.DataFrame(summary).sort_values("mean_hits",ascending=False)
    hdf=pd.DataFrame(hold).sort_values("hits_3281",ascending=False)
    sdf.to_csv(outdir/"current_100_summary.csv",index=False)
    hdf.to_csv(outdir/"holdout_3281.csv",index=False)

    print(f"CURRENT DATASET: {len(df)} draws {df.iloc[0].sorteo}..{df.iloc[-1].sorteo}")
    print("\nLAST-100 FORWARD VALIDATION")
    print(sdf.to_string(index=False))
    print("\nFINAL EXTERNAL HOLDOUT #3281")
    print("actual:", " ".join(map(str,HOLDOUT_3281.tolist())))
    print(hdf.to_string(index=False))

if __name__=="__main__":
    main()
