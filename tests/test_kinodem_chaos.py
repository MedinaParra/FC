import math
from pathlib import Path

import numpy as np

from kinodem_chaos import divergence_series, fit_log_divergence, parse_dump_trajectory


def _frame(step, delta=0.0):
    rows=[]
    for i in range(1,26):
        x=float(i)+delta
        rows.append(f"{i} 1 {x} 0 0 0 0 0 0 0 0 0.02")
    return "\n".join([
        "ITEM: TIMESTEP", str(step),
        "ITEM: NUMBER OF ATOMS", "25",
        "ITEM: BOX BOUNDS ff ff ff", "-10 10", "-10 10", "-10 10",
        "ITEM: ATOMS id type x y z vx vy vz omegax omegay omegaz radius",
        *rows,
    ])+"\n"


def test_parse_trajectory_and_divergence(tmp_path: Path):
    a=tmp_path/"a.dump"; b=tmp_path/"b.dump"
    a.write_text(_frame(0,0)+_frame(10,0))
    b.write_text(_frame(0,0)+_frame(10,0.001))
    ta=parse_dump_trajectory(a)
    tb=parse_dump_trajectory(b)
    rows=divergence_series(ta,tb,1e-5)
    assert len(rows)==2
    assert rows[0]["position_rms_m"]==0
    assert np.isclose(rows[1]["position_rms_m"],0.001)


def test_exponential_fit_recovers_known_rate():
    lam=3.0
    rows=[]
    for k in range(1,21):
        t=0.01*k
        rows.append({
            "time_s": t,
            "position_rms_m": 1e-8*math.exp(lam*t),
        })
    fit=fit_log_divergence(rows,min_value=1e-12)
    assert fit["n_fit"]==20
    assert abs(fit["lambda_1_s"]-lam)<1e-10
    assert fit["r2"]>0.999999
