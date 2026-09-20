import numpy as np

from kino_rail_calibration import fit_circle, projected_arc_pitch


def test_circle_fit_known_arc():
    center=np.array([4.0,-3.0])
    radius=10.0
    a=np.deg2rad(np.array([-40,-30,-20,-10,0,10],dtype=float))
    p=center+radius*np.c_[np.cos(a),np.sin(a)]
    fit=fit_circle(p)
    assert abs(fit["center_x_px"]-4.0)<1e-9
    assert abs(fit["center_y_px"]+3.0)<1e-9
    assert abs(fit["radius_px"]-10.0)<1e-9


def test_projected_pitch_rejects_large_missing_detection_gap():
    center=np.array([0.0,0.0])
    radius=100.0
    # regular 0.1 rad pitch with one missing pair producing a 0.3-rad gap
    a=np.array([0.0,0.1,0.2,0.3,0.6,0.7])
    p=radius*np.c_[np.cos(a),np.sin(a)]
    circle={"center_x_px":0.0,"center_y_px":0.0,"radius_px":100.0}
    out=projected_arc_pitch(p,circle,gap_factor=1.5)
    assert abs(out["local_pitch_px"]-10.0)<1e-9
    assert max(out["accepted_local_intervals_px"])<15.0
