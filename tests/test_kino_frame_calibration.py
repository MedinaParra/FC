import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from kino_frame_calibration import block_statistics, sha256_file


def test_block_statistics_uses_temporal_blocks_not_frames():
    accepted=pd.DataFrame({
        "time_s":[0.01,0.02,0.99,1.01,1.50,2.01],
        "ratio":[12.4,12.6,12.5,13.0,12.8,12.2],
        "quality":[0.8,0.9,0.7,0.8,0.9,0.85],
    })
    b=block_statistics(accepted,1.0)
    assert b["block"].tolist()==[0,1,2]
    assert b["n_frames"].tolist()==[3,2,1]
    assert abs(b.iloc[0]["median_ratio"]-12.5)<1e-12
    assert abs(b.iloc[2]["median_ratio"]-12.2)<1e-12


def test_empty_block_statistics_has_contract():
    b=block_statistics(pd.DataFrame(columns=["time_s","ratio","quality"]),1.0)
    assert len(b)==0
    assert "median_ratio" in b.columns


def test_source_hash_is_exact(tmp_path):
    p=tmp_path/"source.bin"
    p.write_bytes(b"kino-frame-calibration")
    assert sha256_file(p)==hashlib.sha256(b"kino-frame-calibration").hexdigest()
