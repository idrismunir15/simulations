"""Tests for the Vasculature (Windkessel) model."""

import pytest

from cardiovascular_digital_twin.models.vasculature import Vasculature


# ---------------------------------------------------------------------------
# Construction and validation
# ---------------------------------------------------------------------------

def test_default_construction():
    v = Vasculature()
    assert v.resistance == pytest.approx(0.95)
    assert v.compliance == pytest.approx(2.0)
    assert v.venous_pressure == pytest.approx(5.0)


def test_invalid_resistance():
    with pytest.raises(ValueError, match="resistance"):
        Vasculature(resistance=0.0)


def test_invalid_compliance():
    with pytest.raises(ValueError, match="compliance"):
        Vasculature(compliance=-1.0)


def test_invalid_venous_pressure():
    with pytest.raises(ValueError, match="venous_pressure"):
        Vasculature(venous_pressure=-3.0)


# ---------------------------------------------------------------------------
# Time constant
# ---------------------------------------------------------------------------

def test_time_constant():
    v = Vasculature(resistance=1.0, compliance=2.0)
    assert v.time_constant == pytest.approx(2.0, rel=1e-9)


def test_time_constant_proportional_to_r():
    v1 = Vasculature(resistance=1.0, compliance=2.0)
    v2 = Vasculature(resistance=2.0, compliance=2.0)
    assert v2.time_constant == pytest.approx(2 * v1.time_constant, rel=1e-9)


# ---------------------------------------------------------------------------
# ODE right-hand side
# ---------------------------------------------------------------------------

def test_dp_dt_zero_at_equilibrium():
    """
    When Q_in = (P - P_v) / R the system is at equilibrium: dP/dt = 0.
    """
    v = Vasculature(resistance=1.0, compliance=2.0, venous_pressure=5.0)
    P_eq = 5.0 + 80.0 * 1.0  # P_venous + Q * R
    dp = v.dp_dt(pressure=P_eq, flow_in=80.0)
    assert dp == pytest.approx(0.0, abs=1e-10)


def test_dp_dt_positive_when_inflow_exceeds_outflow():
    v = Vasculature(resistance=1.0, compliance=2.0, venous_pressure=5.0)
    # High inflow → pressure should rise
    assert v.dp_dt(80.0, flow_in=200.0) > 0


def test_dp_dt_negative_during_diastole():
    v = Vasculature(resistance=1.0, compliance=2.0, venous_pressure=5.0)
    # No inflow, pressure above venous → pressure should fall
    assert v.dp_dt(120.0, flow_in=0.0) < 0


def test_dp_dt_sign_consistency():
    v = Vasculature(resistance=1.0, compliance=2.0, venous_pressure=5.0)
    # At venous pressure with zero inflow: dP/dt should be zero (or ≈0)
    dp = v.dp_dt(pressure=v.venous_pressure, flow_in=0.0)
    assert dp == pytest.approx(0.0, abs=1e-10)


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------

def test_describe_keys():
    v = Vasculature()
    keys = v.describe().keys()
    assert "peripheral_resistance_mmHg_s_per_mL" in keys
    assert "arterial_compliance_mL_per_mmHg" in keys
    assert "venous_pressure_mmHg" in keys
    assert "rc_time_constant_s" in keys
