#!/usr/bin/env python3
"""Projected extraction-rail calibration from Kino screenshots.

The output is intentionally dimensionless where possible.  Pixel measurements
from a perspective broadcast image are not converted to millimetres without an
independent dimensional anchor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


def sha256_file(path: str | Path) -> str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()


def fit_circle(points: np.ndarray) -> dict:
    p=np.asarray(points,dtype=float)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3:
        raise ValueError("at least three 2D points are required")
    x,y=p[:,0],p[:,1]
    A=np.c_[2*x,2*y,np.ones_like(x)]
    b=x*x+y*y
    cx,cy,c=np.linalg.lstsq(A,b,rcond=None)[0]
    radius=math.sqrt(float(c+cx*cx+cy*cy))
    radial=np.hypot(x-cx,y-cy)
    residual=radial-radius
    return {
        "center_x_px":float(cx),
        "center_y_px":float(cy),
        "radius_px":float(radius),
        "median_abs_residual_px":float(np.median(np.abs(residual))),
        "rms_residual_px":float(np.sqrt(np.mean(residual**2))),
    }


def projected_arc_pitch(points: np.ndarray, circle: dict, gap_factor: float=1.5) -> dict:
    p=np.asarray(points,dtype=float)
    cx,cy=circle["center_x_px"],circle["center_y_px"]
    r=circle["radius_px"]
    a=np.arctan2(p[:,1]-cy,p[:,0]-cx)
    a=np.unwrap(np.sort(a))
    ds=r*np.diff(a)
    if not len(ds):
        raise ValueError("at least two angularly distinct points are required")
    med=float(np.median(ds))
    local=ds[ds <= gap_factor*med]
    if not len(local):
        raise ValueError("no local pitch intervals accepted")
    pitch=float(np.median(local))
    return {
        "all_arc_intervals_px":[float(x) for x in ds],
        "accepted_local_intervals_px":[float(x) for x in local],
        "local_pitch_px":pitch,
        "local_pitch_std_px":float(np.std(local,ddof=1)) if len(local)>1 else 0.0,
        "angular_pitch_deg":float(math.degrees(pitch/r)),
        "rail_radius_over_local_pitch":float(r/pitch),
    }


def detect_rail_balls(image: np.ndarray) -> list[dict]:
    """Detect the visible right/top rail balls in the 10481 camera framing."""
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    yellow=cv2.inRange(hsv,np.array([18,80,80]),np.array([45,255,255]))
    # Fixed-camera ROI derived from screenshot calibration.  The ROI is only a
    # reproducibility aid for this broadcast framing, not a machine dimension.
    x0,y0,x1,y1=760,100,1050,520
    roi=yellow[y0:y1,x0:x1]
    blur=cv2.GaussianBlur(roi,(7,7),1.5)
    circles=cv2.HoughCircles(
        blur,cv2.HOUGH_GRADIENT,dp=1.0,minDist=25,
        param1=80,param2=9,minRadius=12,maxRadius=26
    )
    if circles is None:
        return []
    yy,xx=np.ogrid[:yellow.shape[0],:yellow.shape[1]]
    out=[]
    for x,y,r in circles[0]:
        gx,gy=float(x+x0),float(y+y0)
        # Reject the lower interior ball; retain only the external rail arc.
        if gx <= 830 or gy >= 480:
            continue
        disk=(xx-gx)**2+(yy-gy)**2 <= (0.75*float(r))**2
        fill=float(np.mean(yellow[disk]>0))
        if fill < 0.75:
            continue
        out.append({"x_px":gx,"y_px":gy,"hough_r_px":float(r),"yellow_fill":fill})
    return sorted(out,key=lambda z: math.atan2(z["y_px"]-400,z["x_px"]-657))


def analyze(path: str | Path) -> dict:
    path=Path(path)
    im=cv2.imread(str(path))
    if im is None:
        raise ValueError("image could not be decoded")
    balls=detect_rail_balls(im)
    pts=np.asarray([[b["x_px"],b["y_px"]] for b in balls],dtype=float)
    if len(pts) < 6:
        raise ValueError("insufficient rail-ball detections")
    circle=fit_circle(pts)
    pitch=projected_arc_pitch(pts,circle)
    chamber={
        "center_x_px":683.4000244140625,
        "center_y_px":382.20001220703125,
        "radius_px":282.8399963378906,
    }
    center_offset=math.hypot(
        circle["center_x_px"]-chamber["center_x_px"],
        circle["center_y_px"]-chamber["center_y_px"],
    )
    return {
        "schema":"KinoCFDDEM-v4.1-projected-rail-calibration",
        "source":{"file":path.name,"sha256":sha256_file(path)},
        "detections":balls,
        "rail_center_path":circle,
        "pitch":pitch,
        "reference_outer_chamber":chamber,
        "derived":{
            "rail_radius_over_visible_outer_chamber_radius":
                circle["radius_px"]/chamber["radius_px"],
            "rail_center_offset_px":center_offset,
            "rail_center_offset_over_local_pitch":
                center_offset/pitch["local_pitch_px"],
            "fourteen_center_span_if_local_pitch_persisted_deg":
                13.0*pitch["angular_pitch_deg"],
        },
        "limits":[
            "broadcast perspective projection, not a 3D dimensional survey",
            "local pitch is not asserted to equal true ball diameter",
            "14-ball angular span is an extrapolation, not a measured full-rail endpoint",
            "no millimetre scale has been inferred",
        ],
    }


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out",default="rail_calibration.json")
    args=ap.parse_args()
    result=analyze(args.image)
    Path(args.out).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
