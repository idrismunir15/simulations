"""
Heart model for the cardiovascular digital twin.

The heart is modelled as a pulsatile pump that ejects blood in a periodic
half-sine flow waveform. Key physiological parameters (heart rate, stroke
volume, ejection fraction) are exposed as properties with sensible defaults
for a healthy adult at rest.
"""

import numpy as np


class Heart:
    """
    Lumped-parameter model of the left heart as a pulsatile pump.

    Parameters
    ----------
    heart_rate : float
        Heart rate in beats per minute (bpm). Default 75 bpm.
    stroke_volume : float
        Volume of blood ejected per beat in mL. Default 70 mL.
    systole_fraction : float
        Fraction of the cardiac cycle occupied by systole. Default 0.35.
    end_diastolic_volume : float
        Left ventricular volume at end of filling in mL. Default 120 mL.
    """

    def __init__(
        self,
        heart_rate: float = 75.0,
        stroke_volume: float = 70.0,
        systole_fraction: float = 0.35,
        end_diastolic_volume: float = 120.0,
    ) -> None:
        if heart_rate <= 0:
            raise ValueError("heart_rate must be positive.")
        if stroke_volume <= 0:
            raise ValueError("stroke_volume must be positive.")
        if not 0 < systole_fraction < 1:
            raise ValueError("systole_fraction must be between 0 and 1.")
        if end_diastolic_volume <= stroke_volume:
            raise ValueError("end_diastolic_volume must exceed stroke_volume.")

        self.heart_rate = heart_rate
        self.stroke_volume = stroke_volume
        self.systole_fraction = systole_fraction
        self.end_diastolic_volume = end_diastolic_volume

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def cycle_duration(self) -> float:
        """Duration of one cardiac cycle in seconds."""
        return 60.0 / self.heart_rate

    @property
    def systole_duration(self) -> float:
        """Duration of the systolic (ejection) phase in seconds."""
        return self.systole_fraction * self.cycle_duration

    @property
    def diastole_duration(self) -> float:
        """Duration of the diastolic (filling) phase in seconds."""
        return (1.0 - self.systole_fraction) * self.cycle_duration

    @property
    def cardiac_output(self) -> float:
        """Cardiac output in L/min."""
        return self.heart_rate * self.stroke_volume / 1000.0

    @property
    def ejection_fraction(self) -> float:
        """
        Ejection fraction (dimensionless, 0–1).

        Normal range: 0.55–0.70.
        """
        return self.stroke_volume / self.end_diastolic_volume

    @property
    def end_systolic_volume(self) -> float:
        """Left ventricular volume at end of ejection in mL."""
        return self.end_diastolic_volume - self.stroke_volume

    @property
    def peak_flow_rate(self) -> float:
        """
        Peak aortic flow rate during systole in mL/s.

        Derived so that the integral of the half-sine profile over the
        systolic interval equals the stroke volume exactly:

            ∫₀^T_sys  Q_peak · sin(π t / T_sys) dt  =  SV
            Q_peak  =  π · SV / (2 · T_sys)
        """
        return np.pi * self.stroke_volume / (2.0 * self.systole_duration)

    # ------------------------------------------------------------------
    # Flow waveform
    # ------------------------------------------------------------------

    def flow_rate(self, t: float) -> float:
        """
        Instantaneous aortic flow rate at time *t* in mL/s.

        Uses a half-sine ejection profile during systole and zero flow
        during diastole.  The waveform repeats every cycle.

        Parameters
        ----------
        t : float
            Time in seconds.

        Returns
        -------
        float
            Aortic flow rate in mL/s (≥ 0).
        """
        t_phase = t % self.cycle_duration
        if t_phase < self.systole_duration:
            return self.peak_flow_rate * np.sin(
                np.pi * t_phase / self.systole_duration
            )
        return 0.0

    def flow_rate_array(self, t_array: np.ndarray) -> np.ndarray:
        """Vectorised flow rate over a NumPy time array (mL/s)."""
        return np.array([self.flow_rate(t) for t in t_array])

    # ------------------------------------------------------------------
    # Ventricular volume
    # ------------------------------------------------------------------

    def ventricular_volume(self, t: float) -> float:
        """
        Estimated left ventricular volume at time *t* in mL.

        During systole the volume decreases according to a versed-sine
        profile (consistent with the half-sine flow waveform).  During
        diastole the ventricle refills linearly back to EDV.

        Parameters
        ----------
        t : float
            Time in seconds.

        Returns
        -------
        float
            LV volume in mL.
        """
        T = self.cycle_duration
        t_phase = t % T
        t_sys = self.systole_duration

        if t_phase < t_sys:
            # Versed-sine ejection: V(t) = EDV - SV · (1 - cos(π t/T_sys))/2
            ejected = self.stroke_volume * (1.0 - np.cos(np.pi * t_phase / t_sys)) / 2.0
            return self.end_diastolic_volume - ejected
        else:
            # Linear filling during diastole
            fill_fraction = (t_phase - t_sys) / (T - t_sys)
            return self.end_systolic_volume + self.stroke_volume * fill_fraction

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """Return a human-readable dictionary of heart parameters."""
        return {
            "heart_rate_bpm": self.heart_rate,
            "stroke_volume_mL": self.stroke_volume,
            "cardiac_output_L_per_min": round(self.cardiac_output, 2),
            "ejection_fraction": round(self.ejection_fraction, 3),
            "end_diastolic_volume_mL": self.end_diastolic_volume,
            "end_systolic_volume_mL": self.end_systolic_volume,
            "cycle_duration_s": round(self.cycle_duration, 3),
            "systole_duration_s": round(self.systole_duration, 3),
            "diastole_duration_s": round(self.diastole_duration, 3),
            "peak_flow_rate_mL_per_s": round(self.peak_flow_rate, 1),
        }
