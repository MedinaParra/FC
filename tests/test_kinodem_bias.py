import pytest

from kinodem_bias import P0, build_report, wilson_interval, z_score


def test_bias_report_rejects_invalid_probability_mass():
    summary = {"runs": 10, "counts": [6] * 10 + [5] * 10 + [4] * 5}
    with pytest.raises(ValueError):
        build_report(summary)


def test_bias_report_accepts_exact_14_per_run_mass():
    summary = {"runs": 25, "counts": [14] * 25}
    rows = build_report(summary)
    assert len(rows) == 25
    assert all(r["p_hat"] == P0 for r in rows)
    assert all(abs(r["z"]) < 1e-12 for r in rows)


def test_wilson_and_z_are_finite():
    lo, hi = wilson_interval(56, 100)
    assert 0 <= lo <= 0.56 <= hi <= 1
    assert abs(z_score(56, 100)) < 1e-12
