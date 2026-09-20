import json
import math
from pathlib import Path

import numpy as np

from kinodem_cfdem_case import CFDDEMConfig
from kinocfdem_v4 import (
    CaptureConfig,
    aggregate_capture_summaries,
    detect_capture_events,
    extraction_probe_points,
    summarize_extraction,
    validate_v4_case,
    write_v4_case,
)


def test_v4_case_contains_capture_contract_and_openfoam_probes(tmp_path: Path):
    cfd=CFDDEMConfig(end_time_s=0.002,base_cells=16)
    cap=CaptureConfig(port_radius_m=0.05,sensor_depth_m=0.06)
    case=write_v4_case(tmp_path/"case",cfd,cap)
    v=validate_v4_case(case)
    assert v["ok"]
    assert v["probe_count"]==5
    m=json.loads((case/"case_manifest.json").read_text())
    assert m["model"]=="KinoCFDDEM v4"
    assert m["official_draw_contract"]["balls_loaded"]==25
    assert m["official_draw_contract"]["unique_balls_required"]==14
    assert m["official_draw_contract"]["replacement"] is False
    control=(case/"CFD/system/controlDict").read_text()
    assert "extractionProbes" in control
    assert "fields (p U voidfraction);" in control


def test_capture_probe_points_are_inside_globe():
    cfd=CFDDEMConfig(end_time_s=0.002)
    cap=CaptureConfig()
    pts=extraction_probe_points(cfd,cap)
    assert len(pts)==5
    assert all(np.linalg.norm(p)<cfd.globe_radius_m for p in pts)


def test_detector_produces_unique_ordered_first_entries():
    cfd=CFDDEMConfig(end_time_s=0.01)
    cap=CaptureConfig(
        axis_x=0,axis_y=0,axis_z=1,
        port_radius_m=0.06,
        sensor_depth_m=0.08,
        min_outward_velocity_m_s=0.01,
    )
    # sensor plane z = 0.17, effective center radius = 0.04
    pos0=np.zeros((25,3)); vel0=np.zeros((25,3))
    pos0[:,2]=0.0
    frames={0:{"pos":pos0.copy(),"vel":vel0.copy()}}
    current=pos0.copy()
    velocity=vel0.copy()
    for k in range(1,16):
        current=current.copy(); velocity=velocity.copy()
        idx=k-1
        current[idx]=[0.0,0.0,0.18]
        velocity[idx]=[0.0,0.0,0.5]
        frames[k*10]={"pos":current.copy(),"vel":velocity.copy()}
        # Keep earlier captured particles in the zone; detector must not recount them.
    events=detect_capture_events(frames,1e-5,cfd,cap)
    assert [e["number"] for e in events[:14]]==list(range(1,15))
    assert len({e["number"] for e in events})==len(events)
    s=summarize_extraction(events)
    assert s["complete_14"] is True
    assert s["first_14"]==list(range(1,15))
    assert math.isclose(s["time_to_14_s"],14*10*1e-5)


def test_detector_does_not_count_wrong_direction():
    cfd=CFDDEMConfig(end_time_s=0.01)
    cap=CaptureConfig(port_radius_m=0.06,sensor_depth_m=0.08,min_outward_velocity_m_s=0.1)
    p0=np.zeros((25,3)); v0=np.zeros((25,3))
    p1=p0.copy(); v1=v0.copy()
    p1[0]=[0,0,0.18]
    v1[0]=[0,0,-0.5]
    events=detect_capture_events(
        {0:{"pos":p0,"vel":v0},10:{"pos":p1,"vel":v1}},
        1e-5,cfd,cap,
    )
    assert events==[]


def test_aggregate_only_uses_complete_runs_denominator(tmp_path: Path):
    s1={"summary":{"complete_14":True,"first_14":list(range(1,15))}}
    s2={"summary":{"complete_14":False,"first_14":[1,2,3]}}
    p1=tmp_path/"s1.json"; p2=tmp_path/"s2.json"
    p1.write_text(json.dumps(s1)); p2.write_text(json.dumps(s2))
    r=aggregate_capture_summaries([p1,p2])
    assert r["runs"]==2
    assert r["complete_runs"]==1
    assert r["incomplete_runs"]==1
    assert r["counts_in_first14_complete_runs"][0]==1
    assert r["inclusion_probabilities_complete_runs"][0]==1.0
    assert math.isclose(r["baseline_if_symmetric"],14/25)
