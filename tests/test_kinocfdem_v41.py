from kinocfdem_v41 import validate_v41_case, write_v41_case


def test_v41_retires_rotating_wall_as_real_machine_default(tmp_path):
    root=write_v41_case(tmp_path/"case",end_time_s=0.002,base_cells=16)
    result=validate_v41_case(root)
    cal=result["machine_calibration"]
    assert cal["wall_motion"]=="stationary"
    assert cal["agitation_driver"]=="unresolved non-wall forcing"
    assert result["base"]["base"]["manifest"]["config"]["omega_rad_s"]==0.0
