import json
from pathlib import Path

from kinodem_video_calibration import calibrate


def _doc():
    return {
        "systematic_fraction_for_visual_ratio": 0.08,
        "observations": [
            {
                "quantitative": True,
                "quantity": "globe_diameter_over_ball_diameter",
                "ratio": 12.6,
                "sigma": 1.6,
            },
            {
                "quantitative": True,
                "quantity": "globe_diameter_over_ball_diameter",
                "ratio": 12.5,
                "sigma": 1.6,
            },
            {"quantitative": False, "quantity": "traceability"},
        ],
    }


def test_existing_ratio_is_consistent_with_visual_constraint():
    r = calibrate(_doc(), model_ratio=12.5)
    assert r["n_quantitative_observations"] == 2
    assert r["existing_model_inside_visual_95ci"] is True
    assert 12.4 < r["globe_to_ball_ratio"]["mean"] < 12.7
    assert r["absolute_scale_status"] == "not_identified"


def test_no_absolute_dimensions_without_anchor():
    r = calibrate(_doc())
    assert "scenario_anchor" not in r


def test_scenario_anchor_is_explicitly_not_measurement():
    r = calibrate(_doc(), ball_diameter_mm=40)
    a = r["scenario_anchor"]
    assert a["status"] == "user_or_sensitivity_assumption_not_measurement"
    assert 0.45 < a["implied_globe_diameter_m"] < 0.55
