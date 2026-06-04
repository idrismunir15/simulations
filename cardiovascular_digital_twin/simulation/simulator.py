"""
Numerical simulator for the cardiovascular digital twin.

Uses scipy's ``odeint`` solver to integrate the Windkessel ODE over a
user-specified number of cardiac cycles and derives steady-state
haemodynamic metrics from the last few cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy.integrate import odeint

if TYPE_CHECKING:
    from ..models.cardiovascular_system import CardiovascularSystem


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """
    Container for the outputs of a single simulation run.

    Attributes
    ----------
    time : numpy.ndarray
        Time vector in seconds.
    pressure : numpy.ndarray
        Arterial blood pressure in mmHg at each time step.
    flow : numpy.ndarray
        Aortic (cardiac output) flow rate in mL/s at each time step.
    system : CardiovascularSystem
        The cardiovascular system that produced this result.
    systolic_pressure : float
        Peak arterial pressure in steady state (mmHg).
    diastolic_pressure : float
        Minimum arterial pressure in steady state (mmHg).
    pulse_pressure : float
        Difference between systolic and diastolic pressure (mmHg).
    mean_arterial_pressure : float
        Time-averaged arterial pressure in steady state (mmHg).
    cardiac_output : float
        Time-averaged cardiac output in L/min.
    """

    time: np.ndarray
    pressure: np.ndarray
    flow: np.ndarray
    system: "CardiovascularSystem"

    # Computed metrics (populated by __post_init__)
    systolic_pressure: float = field(init=False)
    diastolic_pressure: float = field(init=False)
    pulse_pressure: float = field(init=False)
    mean_arterial_pressure: float = field(init=False)
    cardiac_output: float = field(init=False)

    def __post_init__(self) -> None:
        self._compute_metrics()

    def _compute_metrics(self) -> None:
        """Derive haemodynamic metrics from the steady-state portion."""
        T = self.system.heart.cycle_duration
        # Skip the first N_SKIP cycles to avoid transient start-up effects
        N_SKIP = 5
        t_start = N_SKIP * T

        mask = self.time >= t_start
        if mask.sum() < 10:
            mask = np.ones(len(self.time), dtype=bool)

        P_ss = self.pressure[mask]
        Q_ss = self.flow[mask]

        self.systolic_pressure = float(np.max(P_ss))
        self.diastolic_pressure = float(np.min(P_ss))
        self.pulse_pressure = self.systolic_pressure - self.diastolic_pressure
        self.mean_arterial_pressure = float(np.mean(P_ss))
        mean_flow_mL_per_s = float(np.mean(Q_ss))
        self.cardiac_output = mean_flow_mL_per_s * 60.0 / 1000.0  # L/min

    def summary(self) -> dict:
        """
        Return a dictionary of key haemodynamic metrics.

        Returns
        -------
        dict
            Keys and values suitable for printing or logging.
        """
        return {
            "systolic_pressure_mmHg": round(self.systolic_pressure, 1),
            "diastolic_pressure_mmHg": round(self.diastolic_pressure, 1),
            "pulse_pressure_mmHg": round(self.pulse_pressure, 1),
            "mean_arterial_pressure_mmHg": round(self.mean_arterial_pressure, 1),
            "cardiac_output_L_per_min": round(self.cardiac_output, 2),
            "heart_rate_bpm": self.system.heart.heart_rate,
            "stroke_volume_mL": self.system.heart.stroke_volume,
            "ejection_fraction": round(self.system.heart.ejection_fraction, 3),
        }


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class Simulator:
    """
    Numerical simulator for a :class:`CardiovascularSystem`.

    Parameters
    ----------
    system : CardiovascularSystem
        The cardiovascular system to simulate.
    """

    def __init__(self, system: "CardiovascularSystem") -> None:
        self.system = system

    def run(
        self,
        n_cycles: int = 15,
        points_per_cycle: int = 200,
        initial_pressure: float = 80.0,
    ) -> SimulationResult:
        """
        Simulate the system for *n_cycles* cardiac cycles.

        The Windkessel ODE is solved using ``scipy.integrate.odeint``.
        The simulation starts from *initial_pressure* and reaches
        periodic steady state after several cycles.

        Parameters
        ----------
        n_cycles : int
            Number of complete cardiac cycles to simulate.
        points_per_cycle : int
            Number of time-discretisation points per cycle.
        initial_pressure : float
            Starting arterial pressure in mmHg.

        Returns
        -------
        SimulationResult
            Time series of pressure and flow, plus derived metrics.
        """
        T = self.system.heart.cycle_duration
        t_end = n_cycles * T
        n_points = n_cycles * points_per_cycle

        t = np.linspace(0.0, t_end, n_points)

        def ode_wrapper(y, t_):
            return [self.system.ode(y[0], t_)]

        P = odeint(ode_wrapper, y0=[initial_pressure], t=t)[:, 0]
        Q = self.system.heart.flow_rate_array(t)

        return SimulationResult(time=t, pressure=P, flow=Q, system=self.system)
