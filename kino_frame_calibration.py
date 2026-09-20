#!/usr/bin/env python3
"""
KinoCFDDEM v4.1 - frame-by-frame visual calibration.

Processes every video frame. The chamber is detected periodically and tracked
between detections; ball diameters are estimated independently in each frame.
No absolute dimensions are inferred unless a separate dimensional anchor exists.

Outputs:
  frame_measurements.csv
  frame_summary.json
  ratio_timeseries.png
  annotated/selected_*.jpg
  contact_sheet.jpg
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def resize_keep(frame, max_width=720):
    h,w=frame.shape[:2]
    if w<=max_width:
        return frame,1.0
    s=max_width/w
    return cv2.resize(frame,(max_width,round(h*s)),interpolation=cv2.INTER_AREA),s


def detect_chambers(frame):
    small,s=resize_keep(frame,720)
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    gray=cv2.GaussianBlur(gray,(9,9),1.5)
    h,w=gray.shape
    circles=cv2.HoughCircles(
        gray,cv2.HOUGH_GRADIENT,dp=1.2,minDist=max(80,h//4),
        param1=120,param2=48,
        minRadius=max(45,int(0.12*h)),maxRadius=int(0.36*h)
    )
    out=[]
    if circles is None:
        return out
    for x,y,r in np.round(circles[0]).astype(int):
        if y-r < -5 or y+r > h+5:
            continue
        out.append((x/s,y/s,r/s))
    return out


def ball_circles(frame,chamber):
    x,y,R=chamber
    h,w=frame.shape[:2]
    x0=max(0,int(x-R)); x1=min(w,int(x+R))
    y0=max(0,int(y-R)); y1=min(h,int(y+R))
    roi=frame[y0:y1,x0:x1]
    if roi.size==0:
        return []
    # Downsample local ROI for stable and fast Hough.
    max_roi=420
    sh=1.0 if roi.shape[1]<=max_roi else max_roi/roi.shape[1]
    rr=cv2.resize(roi,None,fx=sh,fy=sh,interpolation=cv2.INTER_AREA) if sh<1 else roi
    g=cv2.cvtColor(rr,cv2.COLOR_BGR2GRAY)
    g=cv2.medianBlur(g,5)
    Rs=R*sh
    minr=max(3,int(Rs*0.018))
    maxr=max(minr+2,int(Rs*0.075))
    c=cv2.HoughCircles(
        g,cv2.HOUGH_GRADIENT,dp=1.15,minDist=max(6,int(Rs*0.055)),
        param1=105,param2=14,minRadius=minr,maxRadius=maxr
    )
    if c is None:
        return []
    ans=[]
    for cx,cy,cr in c[0]:
        gx=x0+cx/sh; gy=y0+cy/sh; gr=cr/sh
        # Whole ball centre safely within projected chamber.
        if (gx-x)**2+(gy-y)**2 <= (0.92*R)**2:
            ans.append((gx,gy,gr))
    return ans


def choose_chamber(frame,cands,previous=None):
    if not cands:
        return previous,None
    scored=[]
    for c in cands:
        balls=ball_circles(frame,c)
        n=len(balls)
        # Prefer candidates with a physically plausible set of similarly sized circles.
        if n:
            rs=np.array([b[2] for b in balls],float)
            med=np.median(rs)
            cv=np.std(rs)/(med+1e-9)
            plausible=sum((rs>0.45*med)&(rs<1.8*med))
        else:
            cv=9; plausible=0
        continuity=0.0
        if previous is not None:
            px,py,pR=previous
            continuity=math.exp(-math.hypot(c[0]-px,c[1]-py)/(0.35*pR+1e-9))
        score=plausible - 5*min(cv,2) + 3*continuity
        scored.append((score,c,balls))
    scored.sort(key=lambda z:z[0],reverse=True)
    return scored[0][1],scored[0][2]


def robust_ball_radius(balls,R):
    if len(balls)<5:
        return None,0,99.0
    rs=np.array([b[2] for b in balls],float)
    # Broad physical filter independent of target 12.5 ratio.
    rs=rs[(rs>0.015*R)&(rs<0.09*R)]
    if len(rs)<5:
        return None,len(rs),99.0
    med=np.median(rs)
    mad=np.median(np.abs(rs-med))+1e-9
    keep=np.abs(rs-med) <= 2.8*1.4826*mad
    core=rs[keep]
    if len(core)<5:
        return None,len(core),99.0
    return float(np.median(core)),int(len(core)),float(np.std(core)/(np.mean(core)+1e-9))


def annotate(frame,chamber,balls,row):
    im=frame.copy()
    if chamber is not None:
        x,y,R=map(int,chamber)
        cv2.circle(im,(x,y),R,(0,255,255),3)
    for bx,by,br in balls:
        cv2.circle(im,(int(bx),int(by)),int(br),(0,255,0),1)
    txt=f"t={row['time_s']:.3f}s n={row['n_balls']} ratio={row['ratio']:.3f} q={row['quality']:.2f}"
    cv2.rectangle(im,(10,10),(min(im.shape[1]-10,620),48),(0,0,0),-1)
    cv2.putText(im,txt,(18,38),cv2.FONT_HERSHEY_SIMPLEX,0.75,(255,255,255),2,cv2.LINE_AA)
    return im


def sha256_file(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,"rb") as fh:
        while True:
            b=fh.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()


def block_statistics(accepted, block_s=1.0):
    if accepted.empty:
        return pd.DataFrame(columns=[
            "block","start_s","end_s","n_frames","median_ratio",
            "weighted_mean_ratio","median_quality"
        ])
    z=accepted.copy()
    z["block"]=np.floor(z["time_s"]/block_s).astype(int)
    rows=[]
    for b,g in z.groupby("block"):
        w=np.clip(g["quality"].to_numpy(float),0.05,None)
        v=g["ratio"].to_numpy(float)
        rows.append({
            "block":int(b),
            "start_s":float(b*block_s),
            "end_s":float((b+1)*block_s),
            "n_frames":int(len(g)),
            "median_ratio":float(np.median(v)),
            "weighted_mean_ratio":float(np.average(v,weights=w)),
            "median_quality":float(np.median(g["quality"])),
        })
    return pd.DataFrame(rows)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--outdir",default="frame-calibration")
    ap.add_argument("--redetect-every",type=int,default=10)
    ap.add_argument("--max-seconds",type=float,default=0.0,
                    help="Legacy relative duration cap from --start-s")
    ap.add_argument("--start-s",type=float,default=0.0)
    ap.add_argument("--end-s",type=float,default=0.0,
                    help="Absolute end time; 0 means end of video")
    ap.add_argument("--block-s",type=float,default=1.0,
                    help="Temporal block size for correlation-aware summary")
    args=ap.parse_args()
    if args.start_s < 0 or args.end_s < 0 or args.block_s <= 0:
        raise ValueError("start/end must be non-negative and block-s positive")
    if args.end_s and args.end_s <= args.start_s:
        raise ValueError("--end-s must be greater than --start-s")

    out=Path(args.outdir); (out/"annotated").mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(args.video)
    if not cap.isOpened(): raise RuntimeError("Cannot open video")
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    n_total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    source_sha256=sha256_file(args.video)
    start_frame=max(0,int(round(args.start_s*fps)))
    if start_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES,start_frame)
    frame_idx=start_frame
    effective_end=args.end_s
    if args.max_seconds:
        legacy_end=args.start_s+args.max_seconds
        effective_end=min(effective_end,legacy_end) if effective_end else legacy_end
    rows=[]; previous=None; cached_balls=[]

    while True:
        ok,frame=cap.read()
        if not ok: break
        t=frame_idx/fps
        if effective_end and t>effective_end: break

        need_detect=(frame_idx % args.redetect_every==0) or previous is None
        if need_detect:
            cands=detect_chambers(frame)
            chamber,preballs=choose_chamber(frame,cands,previous)
            if chamber is not None:
                previous=chamber
                cached_balls=preballs or []
        chamber=previous
        balls=ball_circles(frame,chamber) if chamber is not None else []
        if not balls and cached_balls:
            balls=cached_balls

        ratio=np.nan; medr=np.nan; ncore=0; rcv=np.nan; q=0.0
        if chamber is not None:
            medr,ncore,rcv=robust_ball_radius(balls,chamber[2])
            if medr:
                ratio=chamber[2]/medr
                count_score=min(1.0,ncore/18.0)
                cv_score=math.exp(-4*min(rcv,1.0))
                ratio_score=1.0 if 7.0<=ratio<=22.0 else 0.15
                q=count_score*cv_score*ratio_score

        rows.append({
            "frame":frame_idx,"time_s":t,
            "chamber_x_px":np.nan if chamber is None else chamber[0],
            "chamber_y_px":np.nan if chamber is None else chamber[1],
            "chamber_radius_px":np.nan if chamber is None else chamber[2],
            "median_ball_radius_px":medr,
            "n_balls":ncore,"ball_radius_cv":rcv,
            "ratio":ratio,"quality":q
        })

        frame_idx+=1
    cap.release()

    df=pd.DataFrame(rows)
    finite=df[np.isfinite(df["ratio"])].copy()
    if len(finite):
        med=float(finite["ratio"].median())
        mad=float(np.median(np.abs(finite["ratio"]-med)))+1e-9
        finite["robust_z"]=np.abs(finite["ratio"]-med)/(1.4826*mad)
        accepted=finite[(finite["quality"]>=0.20)&(finite["robust_z"]<=3.5)&
                        (finite["ratio"]>=7)&(finite["ratio"]<=22)].copy()
    else:
        accepted=finite
    df["accepted"]=False
    if len(accepted):
        df.loc[accepted.index,"accepted"]=True

    df.to_csv(out/"frame_measurements.csv",index=False)
    blocks=block_statistics(accepted,args.block_s)
    blocks.to_csv(out/"block_measurements.csv",index=False)

    if len(accepted):
        vals=accepted["ratio"].to_numpy(float)
        weights=np.clip(accepted["quality"].to_numpy(float),0.05,None)
        mean=float(np.average(vals,weights=weights))
        std=float(np.sqrt(np.average((vals-mean)**2,weights=weights)))
        med=float(np.median(vals))
        q25,q75=np.quantile(vals,[0.25,0.75])
        # Frame correlation inflates sample size; report dispersion, not naive SEM.
        block_vals=blocks["median_ratio"].to_numpy(float)
        summary={
            "video":str(args.video),"source_sha256":source_sha256,
            "fps":fps,"source_total_frames":n_total,
            "start_s":args.start_s,"end_s":effective_end or None,
            "frames_total_processed":len(df),
            "accepted_frames":len(accepted),
            "accepted_fraction":len(accepted)/max(1,len(df)),
            "weighted_mean_ratio":mean,"median_ratio":med,
            "frame_to_frame_std":std,"iqr":[float(q25),float(q75)],
            "min_ratio":float(vals.min()),"max_ratio":float(vals.max()),
            "block_s":args.block_s,
            "accepted_blocks":int(len(blocks)),
            "block_median_ratio":float(np.median(block_vals)),
            "block_std_ratio":float(np.std(block_vals,ddof=1)) if len(block_vals)>1 else 0.0,
            "block_iqr":[float(x) for x in np.quantile(block_vals,[0.25,0.75])],
            "absolute_scale_status":"not_identified",
            "note":"Consecutive video frames are correlated; frame count is not treated as independent metrology samples."
        }
    else:
        summary={
            "video":str(args.video),"source_sha256":source_sha256,
            "fps":fps,"source_total_frames":n_total,
            "start_s":args.start_s,"end_s":effective_end or None,
            "frames_total_processed":len(df),
            "accepted_frames":0,"accepted_blocks":0,
            "block_s":args.block_s,
            "absolute_scale_status":"not_identified",
            "note":"No frames passed automatic quality gates; inspect diagnostics before changing thresholds."
        }
    (out/"frame_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")

    # Plot all valid ratios and accepted subset.
    fig,ax=plt.subplots(figsize=(12,5))
    ax.scatter(finite["time_s"],finite["ratio"],s=5,alpha=.25,label="valid detection")
    if len(accepted):
        ax.scatter(accepted["time_s"],accepted["ratio"],s=7,alpha=.7,label="accepted")
        ax.axhline(summary["median_ratio"],linestyle="--",label=f"median={summary['median_ratio']:.3f}")
    ax.set_xlabel("time [s]"); ax.set_ylabel("D_globe / D_ball")
    ax.set_title("Kino frame-by-frame visual calibration")
    ax.grid(alpha=.2); ax.legend()
    fig.tight_layout(); fig.savefig(out/"ratio_timeseries.png",dpi=160); plt.close(fig)

    # Re-read representative accepted frames: 12 spread over time.
    if len(accepted):
        picks=accepted.iloc[np.linspace(0,len(accepted)-1,min(12,len(accepted))).astype(int)]
        cap=cv2.VideoCapture(args.video); saved=[]
        for k,(_,r) in enumerate(picks.iterrows()):
            idx=int(r["frame"]); cap.set(cv2.CAP_PROP_POS_FRAMES,idx)
            ok,frame=cap.read()
            if not ok: continue
            chamber=(r["chamber_x_px"],r["chamber_y_px"],r["chamber_radius_px"])
            balls=ball_circles(frame,chamber)
            im=annotate(frame,chamber,balls,r)
            p=out/"annotated"/f"selected_{k:02d}_frame_{idx}.jpg"
            cv2.imwrite(str(p),im); saved.append(p)
        cap.release()
        if saved:
            ims=[cv2.imread(str(p)) for p in saved]
            thumb_w=480
            thumbs=[]
            for im in ims:
                s=thumb_w/im.shape[1]
                thumbs.append(cv2.resize(im,(thumb_w,round(im.shape[0]*s))))
            th=max(i.shape[0] for i in thumbs)
            cols=3; rowsn=math.ceil(len(thumbs)/cols)
            sheet=np.full((rowsn*th,cols*thumb_w,3),255,np.uint8)
            for i,im in enumerate(thumbs):
                y=(i//cols)*th; x=(i%cols)*thumb_w
                sheet[y:y+im.shape[0],x:x+thumb_w]=im
            cv2.imwrite(str(out/"contact_sheet.jpg"),sheet)

    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
