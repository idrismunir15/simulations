"""
Combined cardiovascular system model and predefined physiological scenarios.
"""

from .heart import Heart
from .vasculature import Vasculature

# ---------------------------------------------------------------------------
# Predefined physiological scenarios
# ---------------------------------------------------------------------------

SCENARIOS: dict = {
    "normal": {
        "description": "Healthy adult at rest",
        "heart_rate": 75.0,
        "stroke_volume": 70.0,
        "end_diastolic_volume": 120.0,
        "resistance": 0.95,
        "compliance": 2.0,
        "venous_pressure": 5.0,
    },
    "exercise": {
        "description": "Moderate aerobic exercise",
        "heart_rate": 130.0,
        "stroke_volume": 110.0,
        "end_diastolic_volume": 160.0,
        "resistance": 0.45,
        "compliance": 2.0,
        "venous_pressure": 8.0,
    },
    "hypertension": {
        "description": "Stage-2 hypertension",
        "heart_rate": 80.0,
        "stroke_volume": 70.0,
        "end_diastolic_volume": 120.0,
        "resistance": 1.55,
        "compliance": 1.2,
        "venous_pressure": 5.0,
    },
    "heart_failure": {
        "description": "Systolic heart failure (reduced EF)",
        "heart_rate": 95.0,
        "stroke_volume": 35.0,
        "end_diastolic_volume": 180.0,
        "resistance": 1.3,
        "compliance": 2.0,
        "venous_pressure": 12.0,
    },
    "bradycardia": {
        "description": "Sinus bradycardia (slow heart rate)",
        "heart_rate": 45.0,
        "stroke_volume": 90.0,
        "end_diastolic_volume": 130.0,
        "resistance": 0.95,
        "compliance": 2.0,
        "venous_pressure": 5.0,
    },
    "tachycardia": {
        "description": "Sinus tachycardia (fast heart rate)",
        "heart_rate": 150.0,
        "stroke_volume": 55.0,
        "end_diastolic_volume": 110.0,
        "resistance": 0.95,
        "compliance": 1.8,
        "venous_pressure": 5.0,
    },
}


# ---------------------------------------------------------------------------
# Cardiovascular system class
# ---------------------------------------------------------------------------

class CardiovascularSystem:
    """
    Digital twin of the cardiovascular system.

    Combines a :class:`Heart` (pulsatile pump) with a
    :class:`Vasculature` (Windkessel model) to form a closed-loop
    lumped-parameter model of systemic circulation.

    The state variable is arterial blood pressure *P* (mmHg), governed by::

        C · dP/dt = Q_heart(t) − (P − P_venous) / R

    Parameters
    ----------
    heart : Heart
        Cardiac pump model.
    vasculature : Vasculature
        Systemic vascular model.
    """

    def __init__(self, heart: Heart, vasculature: Vasculature) -> None:
        self.heart = heart
        self.vasculature = vasculature
        self.scenario_name: str = "custom"
        self.scenario_description: str = "Custom configuration"

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_scenario(cls, scenario_name: str) -> "CardiovascularSystem":
        """
        Instantiate a system from a named physiological scenario.

        Parameters
        ----------
        scenario_name : str
            One of the keys in :data:`SCENARIOS`:
            ``'normal'``, ``'exercise'``, ``'hypertension'``,
            ``'heart_failure'``, ``'bradycardia'``, ``'tachycardia'``.

        Raises
        ------
        ValueError
            If *scenario_name* is not recognised.
        """
        if scenario_name not in SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{scenario_name}'. "
                f"Available scenarios: {sorted(SCENARIOS.keys())}"
            )
        params = SCENARIOS[scenario_name]
        heart = Heart(
            heart_rate=params["heart_rate"],
            stroke_volume=params["stroke_volume"],
            end_diastolic_volume=params["end_diastolic_volume"],
        )
        vasculature = Vasculature(
            resistance=params["resistance"],
            compliance=params["compliance"],
            venous_pressure=params["venous_pressure"],
        )
        system = cls(heart=heart, vasculature=vasculature)
        system.scenario_name = scenario_name
        system.scenario_description = params["description"]
        return system

    @classmethod
    def normal(cls) -> "CardiovascularSystem":
        """Shortcut: return a system configured for a healthy adult at rest."""
        return cls.from_scenario("normal")

    # ------------------------------------------------------------------
    # ODE interface
    # ------------------------------------------------------------------

    def ode(self, state: float, t: float) -> float:
        """
        ODE right-hand side: dP/dt = f(P, t).

        Parameters
        ----------
        state : float
            Current arterial pressure in mmHg.
        t : float
            Current time in seconds.

        Returns
        -------
        float
            Rate of change of arterial pressure (mmHg/s).
        """
        flow_in = self.heart.flow_rate(t)
        return self.vasculature.dp_dt(pressure=state, flow_in=flow_in)

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """Return a nested dictionary describing the full system."""
        return {
            "scenario": self.scenario_name,
            "description": self.scenario_description,
            "heart": self.heart.describe(),
            "vasculature": self.vasculature.describe(),
        }
