#!/usr/bin/env python3
"""
Prerregistro prospectivo KinoFM para el sorteo #3282.
Usa histórico validado hasta #3280 + resultado observado #3281.
No reentrena ni ajusta después de emitir estas selecciones.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from kinofm_v4 import (
    TimesFM3Scorer, ewma, global_freq, load_csv, previous,
    rolling, to_binary, top14
)

DRAW_3281=[5,6,8,9,10,12,13,14,18,20,21,23,24,25]

def append_3281(df):
    row={"sorteo":3281,"fecha":"18/09/2026"}
    for i,n in enumerate(DRAW_3281,1):
        row[f"n{i}"]=n
    out=pd.concat([df,pd.DataFrame([row])],ignore_index=True)
    return out

def one_baseline(name,fn,y):
    sel=top14(fn(y))
    return {"model":name,"context":None,"selection":" ".join(str(x+1) for x in sel)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv",required=True)
    ap.add_argument("--contexts",default="64,128,256,512")
    ap.add_argument("--device",default="cpu")
    ap.add_argument("--outdir",default="prospective-results")
    args=ap.parse_args()

    contexts=[int(x) for x in args.contexts.split(",")]
    df=append_3281(load_csv(args.csv))
    y=to_binary(df)
    if int(df.iloc[-1].sorteo)!=3281:
        raise RuntimeError("Prospective history must end at #3281")

    rows=[]
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
        rows.append(one_baseline(name,fn,y))

    scorer=TimesFM3Scorer(context=max(contexts),device=args.device)
    model=scorer.model
    tf_scores=[]
    tf_context_rows=[]
    for ctx in contexts:
        x=y[-ctx:].T.astype(np.float32)
        out=list(model.predict_batch(
            contexts=[x],horizon=1,return_quantiles=False,
            use_symmetric_averaging=False
        ))[0]
        scores=np.asarray(out.forecast)[:,0].astype(float)
        sel=top14(scores)
        tf_scores.append(scores)
        rec={
            "model":"TimesFM3","context":ctx,
            "selection":" ".join(str(x+1) for x in sel)
        }
        rows.append(rec)
        tf_context_rows.append(rec)

    avg_scores=np.mean(np.vstack(tf_scores),axis=0)
    consensus=top14(avg_scores)
    rows.append({
        "model":"TimesFM3_mean_score_consensus","context":None,
        "selection":" ".join(str(x+1) for x in consensus)
    })

    outdir=Path(args.outdir); outdir.mkdir(parents=True,exist_ok=True)
    pred=pd.DataFrame(rows)
    pred.to_csv(outdir/"prospective_3282.csv",index=False)

    score_rows=[]
    for n in range(25):
        score_rows.append({
            "number":n+1,
            "mean_timesfm_score":float(avg_scores[n]),
            **{f"score_ctx{ctx}":float(tf_scores[i][n]) for i,ctx in enumerate(contexts)}
        })
    pd.DataFrame(score_rows).sort_values("mean_timesfm_score",ascending=False).to_csv(
        outdir/"prospective_3282_scores.csv",index=False
    )

    print("PROSPECTIVE PREREGISTRATION — KINO #3282")
    print("history_end=3281 date=18/09/2026")
    print(pred.to_string(index=False))

if __name__=="__main__":
    main()
