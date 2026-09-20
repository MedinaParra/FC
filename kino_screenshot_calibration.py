#!/usr/bin/env python3
"""Static screenshot calibration for KinoCFDDEM v4.1.

This tool is deliberately limited to geometry and image registration.
It does not infer velocities without timestamps and must not convert pixels
to millimetres unless an independently measured dimensional anchor is given.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def yellow_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array([18, 90, 90]), np.array([45, 255, 255]))


def detect_outer_chamber(image: np.ndarray) -> tuple[float, float, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
        param1=120, param2=50, minRadius=220, maxRadius=340
    )
    if circles is None:
        raise ValueError("outer chamber circle not detected")
    # The Kino machine is on the left side of the broadcast frame.
    candidates = [c for c in circles[0] if c[0] < image.shape[1] * 0.70]
    if not candidates:
        raise ValueError("no left-side chamber candidate")
    x, y, r = max(candidates, key=lambda c: c[2])
    return float(x), float(y), float(r)


def detect_clear_balls(
    image: np.ndarray,
    chamber: tuple[float, float, float],
    r_min_px: float = 17.0,
    r_max_px: float = 23.0,
    max_normalized_radius: float = 0.80,
    min_yellow_fill: float = 0.90,
) -> list[dict]:
    cx, cy, chamber_r = chamber
    mask = yellow_mask(image)
    blur = cv2.GaussianBlur(mask, (7, 7), 1.5)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.0, minDist=25,
        param1=80, param2=10, minRadius=14, maxRadius=26
    )
    if circles is None:
        return []
    yy, xx = np.ogrid[: image.shape[0], : image.shape[1]]
    out = []
    for x, y, r in circles[0]:
        rho = math.hypot(float(x) - cx, float(y) - cy) / chamber_r
        if rho > max_normalized_radius or not (r_min_px <= r <= r_max_px):
            continue
        disk = (xx - float(x)) ** 2 + (yy - float(y)) ** 2 <= (0.85 * float(r)) ** 2
        fill = float(np.mean(mask[disk] > 0))
        if fill < min_yellow_fill:
            continue
        out.append({
            "x_px": float(x), "y_px": float(y), "r_px": float(r),
            "yellow_fill": fill, "rho": rho,
        })
    return out


def annulus_registration(
    reference: np.ndarray,
    target: np.ndarray,
    chamber: tuple[float, float, float],
) -> dict:
    cx, cy, r = chamber
    yy, xx = np.ogrid[: reference.shape[0], : reference.shape[1]]
    annulus = (
        ((xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2)
        & ((xx - cx) ** 2 + (yy - cy) ** 2 >= (0.72 * r) ** 2)
    )

    def feature_mask(im: np.ndarray) -> np.ndarray:
        no_yellow = yellow_mask(im) == 0
        return (annulus & no_yellow).astype(np.uint8) * 255

    orb = cv2.ORB_create(nfeatures=2000, scaleFactor=1.2, nlevels=8)
    g1 = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    k1, d1 = orb.detectAndCompute(g1, feature_mask(reference))
    k2, d2 = orb.detectAndCompute(g2, feature_mask(target))
    if d1 is None or d2 is None:
        raise ValueError("not enough features for registration")
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = bf.knnMatch(d1, d2, k=2)
    good = [m for m, n in pairs if m.distance < 0.70 * n.distance]
    if len(good) < 8:
        raise ValueError("not enough good feature matches")
    p1 = np.float32([k1[m.queryIdx].pt for m in good])
    p2 = np.float32([k2[m.trainIdx].pt for m in good])
    affine, inliers = cv2.estimateAffinePartial2D(
        p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.0
    )
    if affine is None or inliers is None:
        raise ValueError("registration failed")
    pred = np.hstack([p1, np.ones((len(p1), 1), dtype=np.float32)]) @ affine.T
    residual = np.linalg.norm(pred - p2, axis=1)
    keep = inliers.ravel().astype(bool)
    a, b, tx = affine[0]
    _c, _d, ty = affine[1]
    scale = math.sqrt(float(a * a + b * b))
    rotation_deg = math.degrees(math.atan2(-float(b), float(a)))
    return {
        "good_matches": len(good),
        "inliers": int(np.sum(keep)),
        "scale": scale,
        "rotation_deg": rotation_deg,
        "tx_px": float(tx),
        "ty_px": float(ty),
        "median_inlier_residual_px": float(np.median(residual[keep])),
        "mean_inlier_residual_px": float(np.mean(residual[keep])),
    }


def summarize_ratio(chamber_radius_px: float, frame_ball_radii: list[list[float]]) -> dict:
    per_frame = []
    all_r = []
    for radii in frame_ball_radii:
        if not radii:
            continue
        med = float(np.median(np.asarray(radii, dtype=float)))
        all_r.extend(radii)
        per_frame.append({
            "accepted_balls": len(radii),
            "median_ball_radius_px": med,
            "projected_outer_D_over_ball_d": chamber_radius_px / med,
        })
    if not per_frame:
        raise ValueError("no accepted ball measurements")
    ratios = np.asarray([x["projected_outer_D_over_ball_d"] for x in per_frame])
    all_r = np.asarray(all_r, dtype=float)
    return {
        "accepted_ball_detections": int(len(all_r)),
        "median_ball_radius_px_all_detections": float(np.median(all_r)),
        "frame_equal_weight_ratio_median": float(np.median(ratios)),
        "frame_ratio_min": float(np.min(ratios)),
        "frame_ratio_max": float(np.max(ratios)),
        "per_frame": per_frame,
        "interpretation": (
            "Projected visible outer-shell diameter / apparent ball diameter. "
            "It is not yet the CFD fluid-domain diameter ratio and is not an "
            "absolute dimensional measurement."
        ),
    }


def analyze(paths: list[Path], outdir: Path) -> dict:
    if len(paths) < 2:
        raise ValueError("at least two screenshots are required")
    outdir.mkdir(parents=True, exist_ok=True)
    images = [cv2.imread(str(p)) for p in paths]
    if any(im is None for im in images):
        raise ValueError("one or more images could not be decoded")

    chamber = detect_outer_chamber(images[0])
    ball_rows, frame_radii = [], []
    for path, im in zip(paths, images):
        balls = detect_clear_balls(im, chamber)
        frame_radii.append([b["r_px"] for b in balls])
        for b in balls:
            ball_rows.append({"frame": path.name, **b})

    registrations = []
    for path, im in zip(paths[1:], images[1:]):
        registrations.append({
            "reference": paths[0].name,
            "frame": path.name,
            **annulus_registration(images[0], im, chamber),
        })

    ratio = summarize_ratio(chamber[2], frame_radii)
    summary = {
        "schema": "KinoCFDDEM-v4.1-screenshot-calibration",
        "sources": [{"file": p.name, "sha256": sha256_file(p)} for p in paths],
        "reference_outer_chamber": {
            "frame": paths[0].name,
            "center_x_px": chamber[0],
            "center_y_px": chamber[1],
            "radius_px": chamber[2],
            "diameter_px": 2.0 * chamber[2],
        },
        "ratio": ratio,
        "registration": registrations,
        "physics_constraints": {
            "absolute_scale_identified": False,
            "temporal_velocity_identified": False,
            "rotating_wall_supported_by_these_frames": False,
            "recommended_default_wall_motion": "stationary",
            "agitation_driver": "unresolved; non-wall forcing required",
        },
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if ball_rows:
        with (outdir / "ball_measurements.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(ball_rows[0]))
            w.writeheader(); w.writerows(ball_rows)
    if registrations:
        with (outdir / "registration.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(registrations[0]))
            w.writeheader(); w.writerows(registrations)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("kino-screenshot-calibration"))
    args = ap.parse_args()
    print(json.dumps(analyze(args.images, args.outdir), indent=2))


if __name__ == "__main__":
    main()
