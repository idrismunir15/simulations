"""Tests for the Heart model."""

import pytest
import numpy as np

from cardiovascular_digital_twin.models.heart import Heart


# ---------------------------------------------------------------------------
# Construction and validation
# ---------------------------------------------------------------------------

def test_default_construction():
    h = Heart()
    assert h.heart_rate == 75.0
    assert h.stroke_volume == 70.0


def test_invalid_heart_rate():
    with pytest.raises(ValueError, match="heart_rate"):
        Heart(heart_rate=0)


def test_invalid_stroke_volume():
    with pytest.raises(ValueError, match="stroke_volume"):
        Heart(stroke_volume=-5)


def test_invalid_systole_fraction():
    with pytest.raises(ValueError, match="systole_fraction"):
        Heart(systole_fraction=1.2)


def test_invalid_edv_less_than_sv():
    with pytest.raises(ValueError, match="end_diastolic_volume"):
        Heart(stroke_volume=80, end_diastolic_volume=60)


# ---------------------------------------------------------------------------
# Derived properties
# ---------------------------------------------------------------------------

def test_cardiac_output():
    h = Heart(heart_rate=75, stroke_volume=70)
    assert h.cardiac_output == pytest.approx(75 * 70 / 1000, rel=1e-9)


def test_ejection_fraction():
    h = Heart(stroke_volume=70, end_diastolic_volume=120)
    assert h.ejection_fraction == pytest.approx(70 / 120, rel=1e-9)
    assert 0 < h.ejection_fraction < 1


def test_cycle_duration():
    h = Heart(heart_rate=60)
    assert h.cycle_duration == pytest.approx(1.0, rel=1e-9)


def test_systole_duration():
    h = Heart(heart_rate=75, systole_fraction=0.35)
    assert h.systole_duration == pytest.approx(0.35 * h.cycle_duration, rel=1e-9)


def test_systole_plus_diastole_equals_cycle():
    h = Heart()
    assert h.systole_duration + h.diastole_duration == pytest.approx(
        h.cycle_duration, rel=1e-9
    )


def test_end_systolic_volume():
    h = Heart(stroke_volume=70, end_diastolic_volume=120)
    assert h.end_systolic_volume == pytest.approx(50.0, rel=1e-9)


# ---------------------------------------------------------------------------
# Flow waveform
# ---------------------------------------------------------------------------

def test_flow_positive_at_mid_systole():
    h = Heart(heart_rate=75, stroke_volume=70)
    Q = h.flow_rate(0.5 * h.systole_duration)
    assert Q > 0


def test_flow_zero_at_diastole():
    h = Heart(heart_rate=75, stroke_volume=70)
    Q = h.flow_rate(0.9 * h.cycle_duration)
    assert Q == pytest.approx(0.0, abs=1e-12)


def test_flow_integral_equals_stroke_volume():
    """Integral of flow over one systolic interval must equal stroke volume."""
    h = Heart(heart_rate=75, stroke_volume=70)
    t = np.linspace(0, h.systole_duration, 50_000)
    Q = h.flow_rate_array(t)
    sv_computed = float(np.trapezoid(Q, t))
    assert sv_computed == pytest.approx(70.0, rel=0.005)


def test_flow_periodic():
    """Flow at equivalent phase in two consecutive cycles must be identical."""
    h = Heart(heart_rate=75, stroke_volume=70)
    T = h.cycle_duration
    t_test = 0.15 * h.systole_duration
    assert h.flow_rate(t_test) == pytest.approx(h.flow_rate(t_test + T), rel=1e-9)


# ---------------------------------------------------------------------------
# Ventricular volume
# ---------------------------------------------------------------------------

def test_ventricular_volume_max_is_edv():
    h = Heart(heart_rate=75, stroke_volume=70, end_diastolic_volume=120)
    T = h.cycle_duration
    t_arr = np.linspace(0, T, 2000)
    V = [h.ventricular_volume(t) for t in t_arr]
    assert max(V) == pytest.approx(h.end_diastolic_volume, rel=0.01)


def test_ventricular_volume_min_is_esv():
    h = Heart(heart_rate=75, stroke_volume=70, end_diastolic_volume=120)
    T = h.cycle_duration
    t_arr = np.linspace(0, T, 2000)
    V = [h.ventricular_volume(t) for t in t_arr]
    assert min(V) >= h.end_systolic_volume - 1.0


def test_describe_keys():
    expected = {
        "heart_rate_bpm",
        "stroke_volume_mL",
        "cardiac_output_L_per_min",
        "ejection_fraction",
        "cycle_duration_s",
        "systole_duration_s",
        "peak_flow_rate_mL_per_s",
    }
    h = Heart()
    assert expected.issubset(h.describe().keys())
