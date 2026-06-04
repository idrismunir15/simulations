"""Tests for the Simulator and CardiovascularSystem."""

import pytest

from cardiovascular_digital_twin.models.cardiovascular_system import (
    CardiovascularSystem,
    SCENARIOS,
)
from cardiovascular_digital_twin.simulation.simulator import Simulator, SimulationResult


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------

def test_all_scenario_names_present():
    expected = {"normal", "exercise", "hypertension", "heart_failure",
                "bradycardia", "tachycardia"}
    assert expected == set(SCENARIOS.keys())


def test_invalid_scenario_raises():
    with pytest.raises(ValueError, match="Unknown scenario"):
        CardiovascularSystem.from_scenario("nonexistent")


def test_normal_classmethod():
    sys = CardiovascularSystem.normal()
    assert sys.scenario_name == "normal"


def test_scenario_description_populated():
    for name in SCENARIOS:
        sys = CardiovascularSystem.from_scenario(name)
        assert sys.scenario_description  # non-empty


# ---------------------------------------------------------------------------
# Simulation output structure
# ---------------------------------------------------------------------------

def _quick_result(scenario: str = "normal", n_cycles: int = 15):
    system = CardiovascularSystem.from_scenario(scenario)
    return Simulator(system).run(n_cycles=n_cycles)


def test_result_is_simulation_result():
    assert isinstance(_quick_result(), SimulationResult)


def test_result_arrays_same_length():
    r = _quick_result()
    assert len(r.time) == len(r.pressure) == len(r.flow)


def test_result_time_starts_at_zero():
    r = _quick_result()
    assert r.time[0] == pytest.approx(0.0)


def test_result_pressure_positive():
    r = _quick_result()
    assert all(r.pressure > 0)


def test_result_flow_non_negative():
    r = _quick_result()
    assert all(r.flow >= -1e-10)  # small numerical tolerance


def test_summary_keys():
    r = _quick_result()
    required = {
        "systolic_pressure_mmHg",
        "diastolic_pressure_mmHg",
        "pulse_pressure_mmHg",
        "mean_arterial_pressure_mmHg",
        "cardiac_output_L_per_min",
        "heart_rate_bpm",
        "stroke_volume_mL",
        "ejection_fraction",
    }
    assert required.issubset(r.summary().keys())


# ---------------------------------------------------------------------------
# Physiological plausibility — normal scenario
# ---------------------------------------------------------------------------

def test_normal_systolic_pressure_range():
    r = _quick_result("normal")
    assert 90 < r.systolic_pressure < 145, (
        f"Systolic pressure {r.systolic_pressure:.1f} outside expected range"
    )


def test_normal_diastolic_pressure_range():
    r = _quick_result("normal")
    assert 60 < r.diastolic_pressure < 100, (
        f"Diastolic pressure {r.diastolic_pressure:.1f} outside expected range"
    )


def test_normal_cardiac_output_range():
    r = _quick_result("normal")
    assert 3.5 < r.cardiac_output < 7.0, (
        f"Cardiac output {r.cardiac_output:.2f} L/min outside expected range"
    )


def test_systolic_greater_than_diastolic():
    for name in SCENARIOS:
        r = _quick_result(name)
        assert r.systolic_pressure > r.diastolic_pressure, (
            f"Scenario '{name}': systolic ≤ diastolic"
        )


def test_pulse_pressure_equals_difference():
    r = _quick_result("normal")
    assert r.pulse_pressure == pytest.approx(
        r.systolic_pressure - r.diastolic_pressure, rel=1e-6
    )


def test_map_between_diastolic_and_systolic():
    r = _quick_result("normal")
    assert r.diastolic_pressure < r.mean_arterial_pressure < r.systolic_pressure


# ---------------------------------------------------------------------------
# Comparative physiology
# ---------------------------------------------------------------------------

def test_hypertension_higher_pressure_than_normal():
    r_n = _quick_result("normal")
    r_h = _quick_result("hypertension")
    assert r_h.systolic_pressure > r_n.systolic_pressure
    assert r_h.diastolic_pressure > r_n.diastolic_pressure


def test_exercise_higher_cardiac_output_than_normal():
    r_n = _quick_result("normal")
    r_e = _quick_result("exercise")
    assert r_e.cardiac_output > r_n.cardiac_output


def test_heart_failure_lower_stroke_volume_than_normal():
    normal_sys = CardiovascularSystem.from_scenario("normal")
    hf_sys = CardiovascularSystem.from_scenario("heart_failure")
    assert hf_sys.heart.stroke_volume < normal_sys.heart.stroke_volume


def test_bradycardia_lower_heart_rate_than_normal():
    normal_sys = CardiovascularSystem.from_scenario("normal")
    brady_sys = CardiovascularSystem.from_scenario("bradycardia")
    assert brady_sys.heart.heart_rate < normal_sys.heart.heart_rate


def test_tachycardia_higher_heart_rate_than_normal():
    normal_sys = CardiovascularSystem.from_scenario("normal")
    tachy_sys = CardiovascularSystem.from_scenario("tachycardia")
    assert tachy_sys.heart.heart_rate > normal_sys.heart.heart_rate


# ---------------------------------------------------------------------------
# All scenarios run without error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", list(SCENARIOS.keys()))
def test_scenario_runs_without_error(scenario):
    r = _quick_result(scenario)
    assert r.cardiac_output > 0
