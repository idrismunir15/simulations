"""
Vascular model for the cardiovascular digital twin.

The systemic vasculature is represented by a two-element Windkessel model
(resistance R in parallel with compliance C).  This is the simplest lumped
parameter model that captures the key features of arterial blood pressure:
the exponential diastolic run-off and pulse-pressure amplification.

Governing ODE
-------------
    C · dP/dt = Q_in(t) − (P − P_venous) / R

where
    C           arterial compliance   [mL/mmHg]
    P           arterial pressure     [mmHg]
    R           peripheral resistance [mmHg·s/mL]
    Q_in        cardiac inflow        [mL/s]
    P_venous    venous back-pressure  [mmHg]
"""


class Vasculature:
    """
    Two-element Windkessel model of the systemic vasculature.

    Parameters
    ----------
    resistance : float
        Total peripheral (systemic vascular) resistance in mmHg·s/mL.
        Typical resting value ≈ 0.95 mmHg·s/mL.
    compliance : float
        Total arterial compliance in mL/mmHg.
        Typical resting value ≈ 2.0 mL/mmHg.
    venous_pressure : float
        Central venous (back-)pressure in mmHg.
        Typical resting value ≈ 5 mmHg.
    """

    def __init__(
        self,
        resistance: float = 0.95,
        compliance: float = 2.0,
        venous_pressure: float = 5.0,
    ) -> None:
        if resistance <= 0:
            raise ValueError("resistance must be positive.")
        if compliance <= 0:
            raise ValueError("compliance must be positive.")
        if venous_pressure < 0:
            raise ValueError("venous_pressure must be non-negative.")

        self.resistance = resistance
        self.compliance = compliance
        self.venous_pressure = venous_pressure

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def time_constant(self) -> float:
        """
        RC time constant in seconds.

        This determines how quickly arterial pressure decays during
        diastole (when cardiac inflow is zero).
        """
        return self.resistance * self.compliance

    # ------------------------------------------------------------------
    # ODE right-hand side
    # ------------------------------------------------------------------

    def dp_dt(self, pressure: float, flow_in: float) -> float:
        """
        Compute the rate of change of arterial pressure.

        Parameters
        ----------
        pressure : float
            Current arterial pressure in mmHg.
        flow_in : float
            Current cardiac inflow rate in mL/s.

        Returns
        -------
        float
            dP/dt in mmHg/s.
        """
        return (flow_in - (pressure - self.venous_pressure) / self.resistance) / self.compliance

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """Return a human-readable dictionary of vascular parameters."""
        return {
            "peripheral_resistance_mmHg_s_per_mL": self.resistance,
            "arterial_compliance_mL_per_mmHg": self.compliance,
            "venous_pressure_mmHg": self.venous_pressure,
            "rc_time_constant_s": round(self.time_constant, 3),
        }
