import json
from pathlib import Path

import numpy as np

from kinodem_liggghts import (
    LiggghtsConfig,
    N_BALLS,
    N_DRAW,
    generate_initial_state,
    load_ball_calibration_csv,
    parse_last_dump,
    parse_timestep_metrics,
    prepare_case,
    select_from_state,
)


def test_initial_state_is_inside_and_nonoverlapping():
    cfg = LiggghtsConfig(seconds=0.001)
    pos, vel = generate_initial_state(cfg, 123)
    assert pos.shape == (N_BALLS, 3)
    assert vel.shape == (N_BALLS, 3)
    assert cfg.geometry == "globe"
    radius = np.linalg.norm(pos, axis=1)
    assert np.all(radius + cfg.ball_radius < cfg.drum_radius)
    for i in range(N_BALLS):
        for j in range(i + 1, N_BALLS):
            assert np.linalg.norm(pos[i] - pos[j]) > 2 * cfg.ball_radius


def test_prepare_case_contains_real_liggghts_commands(tmp_path: Path):
    cfg = LiggghtsConfig(seconds=0.001)
    prepare_case(tmp_path, cfg, 9)
    inp = (tmp_path / "in.kinodem").read_text()
    assert "pair_style gran model hertz tangential history" in inp
    assert "fix drum all mesh/surface" in inp
    assert "surface_ang_vel" in inp
    assert "fix wall all wall/gran" in inp
    assert "fix integr all nve/sphere" in inp
    assert "fix ts_check all check/timestep/gran" in inp
    assert "f_ts_check[1] f_ts_check[2] f_ts_check[3]" in inp
    mesh = (tmp_path / "drum.stl").read_text()
    assert mesh.startswith("solid kinodem_globe")
    assert mesh.count("facet normal") == 2 * cfg.drum_segments * (cfg.globe_lat_segments + 1) - 4
    vertices = []
    for line in mesh.splitlines():
        if line.strip().startswith("vertex "):
            _, x, y, z = line.split()
            vertices.append((float(x), float(y), float(z)))
    min_axis_radius = min((x*x + y*y) ** 0.5 for x, y, _ in vertices)
    assert min_axis_radius >= 0.0099 * cfg.drum_radius
    assert (tmp_path / "drum.stl").stat().st_size > 1000
    data = (tmp_path / "balls.data").read_text()
    assert "25 atoms" in data
    assert "Atoms" in data and "Velocities" in data


def test_parse_last_dump_uses_last_frame_and_ids(tmp_path: Path):
    path = tmp_path / "state.dump"
    def frame(step, offset):
        rows = []
        for i in range(1, 26):
            rows.append(f"{i} 1 {i+offset} 0 0 0 0 0 0 0 0 0.02")
        return "\n".join([
            "ITEM: TIMESTEP", str(step), "ITEM: NUMBER OF ATOMS", "25",
            "ITEM: BOX BOUNDS ff ff ff", "-1 1", "-1 1", "-1 1",
            "ITEM: ATOMS id type x y z vx vy vz omegax omegay omegaz radius",
            *rows,
        ]) + "\n"
    path.write_text(frame(0, 0) + frame(10, 100))
    state = parse_last_dump(path)
    assert state[1]["x"] == 101
    assert state[25]["x"] == 125


def test_selection_is_exactly_14_unique_numbers():
    cfg = LiggghtsConfig(outlet_angle_deg=0.0)
    state = {}
    for i in range(1, 26):
        state[i] = {"x": float(i), "y": 0.0, "z": 0.0, "vx": 0.0, "vy": 0.0, "vz": 0.0}
    selected = select_from_state(state, cfg)
    assert len(selected) == N_DRAW
    assert len(set(selected)) == N_DRAW
    assert selected == list(range(12, 26))


def test_legacy_cylinder_geometry_remains_supported():
    cfg = LiggghtsConfig(geometry="cylinder", seconds=0.001)
    pos, _ = generate_initial_state(cfg, 321)
    radial = np.linalg.norm(pos[:, :2], axis=1)
    assert np.all(radial + cfg.ball_radius < cfg.drum_radius)
    assert np.all(np.abs(pos[:, 2]) + cfg.ball_radius < cfg.drum_depth / 2)


def test_measured_ball_calibration_is_written_per_particle(tmp_path: Path):
    csv_path = tmp_path / "balls.csv"
    rows = ["number,diameter_m,mass_kg"]
    for i in range(1, 26):
        diameter = 0.039 if i == 1 else 0.040
        mass = 0.0038 if i == 1 else 0.0040
        rows.append(f"{i},{diameter},{mass}")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    specs = load_ball_calibration_csv(csv_path)
    assert len(specs) == 25
    assert specs[0].number == 1
    assert specs[0].diameter_m == 0.039
    assert specs[0].mass_kg == 0.0038

    cfg = LiggghtsConfig(seconds=0.001)
    case = prepare_case(tmp_path / "case", cfg, 17, specs)
    data_lines = (case / "balls.data").read_text().splitlines()
    atom1 = next(line for line in data_lines if line.startswith("1 1 "))
    parts = atom1.split()
    assert float(parts[2]) == 0.039
    expected_density = specs[0].density_kg_m3
    assert np.isclose(float(parts[3]), expected_density, rtol=1e-10)

    metadata = json.loads((case / "case.json").read_text())
    assert metadata["balls"][0]["number"] == 1
    assert metadata["balls"][0]["diameter_m"] == 0.039
    assert np.isclose(metadata["balls"][0]["density_kg_m3"], expected_density)


def test_parse_timestep_metrics(tmp_path: Path):
    log = tmp_path / "liggghts.stdout.log"
    log.write_text(
        """
LIGGGHTS test
    Step    Atoms    KinEng    ts_check    ts_check    ts_check
       0       25      0.01            0            0            0
      20       25      0.01      0.00650      0.00190      0.00120
      40       25      0.01      0.00670      0.00210      0.00150
Loop time of 0.1 on 1 procs
""",
        encoding="utf-8",
    )
    m = parse_timestep_metrics(log)
    assert m["max_dt_over_rayleigh"] == 0.00670
    assert m["max_dt_over_hertz"] == 0.00210
    assert m["max_relative_travel_over_skin"] == 0.00150
    assert m["max_dt_over_rayleigh"] < m["rayleigh_limit"]
    assert m["max_dt_over_hertz"] < m["hertz_limit"]
    assert m["max_relative_travel_over_skin"] < m["skin_limit"]
