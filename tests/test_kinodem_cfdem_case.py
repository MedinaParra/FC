from pathlib import Path
import json
import math

from kinodem_cfdem_case import CFDDEMConfig, validate_case, write_case


def test_generate_two_way_cfdem_case(tmp_path: Path):
    cfg=CFDDEMConfig(end_time_s=0.002,base_cells=16)
    case=write_case(tmp_path/"case",cfg)
    result=validate_case(case)
    assert result["ok"]
    cp=(case/"CFD/constant/couplingProperties").read_text()
    dem=(case/"DEM/in.liggghts_run").read_text()
    u=(case/"CFD/0/U").read_text()
    assert "dataExchangeModel twoWayMPI;" in cp
    assert "couplingInterval 10;" in cp
    assert "liggghtsPath \"../DEM/in.liggghts_run\";" in cp
    assert "fix cfd all couple/cfd couple_every 10 mpi" in dem
    assert "fix cfd2 all couple/cfd/force" in dem
    assert "rotatingWallVelocity" in u
    assert "omega 7;" in u


def test_time_step_contract_is_exact():
    cfg=CFDDEMConfig(dem_dt_s=1e-5,coupling_interval=10,end_time_s=0.002)
    assert math.isclose(cfg.cfd_dt_s,1e-4)


def test_manifest_marks_rotation_as_hypothesis(tmp_path: Path):
    case=write_case(tmp_path/"case",CFDDEMConfig(end_time_s=0.002,base_cells=16))
    m=json.loads((case/"case_manifest.json").read_text())
    assert m["agitation_hypothesis"]=="rotating globe wall"
    assert "not_yet_a_validated_real-kino" in m["status"]
