from pathlib import Path

import numpy as np

from kinodem_liggghts import (
    LiggghtsConfig,
    N_BALLS,
    N_DRAW,
    generate_initial_state,
    parse_last_dump,
    prepare_case,
    select_from_state,
)


def test_initial_state_is_inside_and_nonoverlapping():
    cfg = LiggghtsConfig(seconds=0.001)
    pos, vel = generate_initial_state(cfg, 123)
    assert pos.shape == (N_BALLS, 3)
    assert vel.shape == (N_BALLS, 3)
    radial = np.linalg.norm(pos[:, :2], axis=1)
    assert np.all(radial + cfg.ball_radius < cfg.drum_radius)
    assert np.all(np.abs(pos[:, 2]) + cfg.ball_radius < cfg.drum_depth / 2)
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
