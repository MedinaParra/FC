import math
import numpy as np
import pytest

from kinodem_v1 import (
    N_BALLS,
    N_DRAW,
    DrumConfig,
    KinoDEMSimulator,
    monte_carlo,
)


def test_initialize_has_25_nonoverlapping_balls_inside_drum():
    sim = KinoDEMSimulator(drum=DrumConfig(mix_seconds=0.03, dt=0.003))
    rng = np.random.default_rng(123)
    pos, vel = sim.initialize(rng)
    assert pos.shape == (N_BALLS, 2)
    assert vel.shape == (N_BALLS, 2)

    for i in range(N_BALLS):
        assert np.linalg.norm(pos[i]) + sim.radii[i] <= sim.drum.radius + 1e-9
        for j in range(i + 1, N_BALLS):
            assert np.linalg.norm(pos[i] - pos[j]) > sim.radii[i] + sim.radii[j]


def test_run_is_reproducible_and_selects_14_unique_numbers():
    sim = KinoDEMSimulator(drum=DrumConfig(mix_seconds=0.03, dt=0.003))
    a, _, _ = sim.run(777)
    b, _, _ = sim.run(777)
    assert np.array_equal(a, b)
    assert len(a) == N_DRAW
    assert len(set(a.tolist())) == N_DRAW
    assert np.all((a >= 1) & (a <= N_BALLS))


def test_step_keeps_finite_state_inside_drum():
    sim = KinoDEMSimulator(drum=DrumConfig(mix_seconds=0.03, dt=0.003))
    pos, vel = sim.initialize(np.random.default_rng(44))
    for _ in range(30):
        sim.step(pos, vel)
    assert np.isfinite(pos).all()
    assert np.isfinite(vel).all()
    assert np.all(np.linalg.norm(pos, axis=1) + sim.radii <= sim.drum.radius + 1e-8)


def test_monte_carlo_probability_mass_is_exactly_14():
    result = monte_carlo(
        runs=5,
        seed=20260919,
        drum=DrumConfig(mix_seconds=0.018, dt=0.003),
    )
    probs = np.asarray(result["probabilities"])
    assert probs.shape == (N_BALLS,)
    assert math.isclose(probs.sum(), N_DRAW, abs_tol=1e-12)
    assert sum(result["counts"]) == 5 * N_DRAW
    assert len(result["draws"]) == 5


def test_invalid_run_count_rejected():
    with pytest.raises(ValueError):
        monte_carlo(0)
