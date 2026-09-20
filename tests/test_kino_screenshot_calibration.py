import hashlib
import numpy as np

from kino_screenshot_calibration import sha256_file, summarize_ratio


def test_sha256_exact(tmp_path):
    p=tmp_path/"a.bin"
    p.write_bytes(b"kino3281")
    assert sha256_file(p)==hashlib.sha256(b"kino3281").hexdigest()


def test_ratio_is_frame_equal_weighted():
    s=summarize_ratio(100.0, [[10.0,10.0,10.0],[8.0]])
    # per-frame ratios are 10 and 12.5; median is 11.25
    assert abs(s["frame_equal_weight_ratio_median"]-11.25)<1e-12
    assert s["accepted_ball_detections"]==4


def test_ratio_contract_marks_projection_not_absolute():
    s=summarize_ratio(100.0, [[10.0],[10.0]])
    assert "Projected visible outer-shell" in s["interpretation"]
