"""
Visualization module for the cardiovascular digital twin.

Provides three plotting functions:

plot_simulation
    Pressure and flow time-series for a single scenario.

plot_comparison
    Side-by-side comparison of multiple scenarios.

plot_pv_loop
    Idealised left-ventricular pressure–volume (PV) loop constructed
    from heart and vasculature parameters.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")  # non-interactive backend; caller may override before import
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

if TYPE_CHECKING:
    from ..simulation.simulator import SimulationResult
    from ..models.cardiovascular_system import CardiovascularSystem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _steady_state_slice(result: "SimulationResult", n_cycles: int = 3):
    """Return time and signal arrays for the last *n_cycles* steady-state cycles."""
    T = result.system.heart.cycle_duration
    t_start = max(0.0, result.time[-1] - n_cycles * T)
    mask = result.time >= t_start
    t = result.time[mask] - t_start
    return t, result.pressure[mask], result.flow[mask]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_simulation(
    result: "SimulationResult",
    n_cycles_to_show: int = 3,
    title: Optional[str] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Plot arterial pressure and aortic flow for a simulation result.

    Parameters
    ----------
    result : SimulationResult
        Output of :meth:`Simulator.run`.
    n_cycles_to_show : int
        Number of steady-state cycles to include in the plot.
    title : str, optional
        Figure title; auto-generated when omitted.
    save_path : str, optional
        If given, the figure is saved to this file path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    t, P, Q = _steady_state_slice(result, n_cycles_to_show)
    summary = result.summary()

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # --- Pressure panel ---
    ax1 = axes[0]
    ax1.plot(t, P, color="#1f77b4", linewidth=2, label="Arterial Pressure")
    ax1.axhline(
        summary["systolic_pressure_mmHg"],
        color="crimson", linestyle="--", alpha=0.8,
        label=f"Systolic: {summary['systolic_pressure_mmHg']} mmHg",
    )
    ax1.axhline(
        summary["diastolic_pressure_mmHg"],
        color="seagreen", linestyle="--", alpha=0.8,
        label=f"Diastolic: {summary['diastolic_pressure_mmHg']} mmHg",
    )
    ax1.axhline(
        summary["mean_arterial_pressure_mmHg"],
        color="darkorange", linestyle=":", alpha=0.8,
        label=f"MAP: {summary['mean_arterial_pressure_mmHg']} mmHg",
    )
    ax1.set_ylabel("Pressure (mmHg)", fontsize=12)
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(bottom=0)

    # --- Flow panel ---
    ax2 = axes[1]
    ax2.plot(t, Q, color="firebrick", linewidth=2, label="Aortic Flow")
    ax2.fill_between(t, Q, alpha=0.25, color="firebrick")
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_xlabel("Time (s)", fontsize=12)
    ax2.set_ylabel("Flow (mL/s)", fontsize=12)
    ax2.set_ylim(bottom=-5)
    ax2.text(
        0.02, 0.93,
        f"CO: {summary['cardiac_output_L_per_min']} L/min  |  "
        f"HR: {summary['heart_rate_bpm']} bpm  |  "
        f"SV: {summary['stroke_volume_mL']} mL",
        transform=ax2.transAxes, fontsize=10, verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.6),
    )
    ax2.grid(True, alpha=0.3)

    if title is None:
        desc = getattr(result.system, "scenario_description", "Custom")
        title = (
            f"Cardiovascular Digital Twin — {desc}\n"
            f"BP {summary['systolic_pressure_mmHg']}/{summary['diastolic_pressure_mmHg']} mmHg  "
            f"(PP {summary['pulse_pressure_mmHg']} mmHg)"
        )
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_comparison(
    results: List["SimulationResult"],
    labels: Optional[List[str]] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Create a side-by-side comparison of multiple simulation results.

    Parameters
    ----------
    results : list of SimulationResult
        Each element is one scenario to compare.
    labels : list of str, optional
        Display labels corresponding to each result.
    save_path : str, optional
        If given, the figure is saved to this file path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    n = len(results)
    if labels is None:
        labels = [
            getattr(r.system, "scenario_name", f"Scenario {i + 1}")
            for i, r in enumerate(results)
        ]

    fig, axes = plt.subplots(2, n, figsize=(5 * n, 8), sharey="row")
    if n == 1:
        axes = axes.reshape(2, 1)

    colours = plt.cm.tab10(np.linspace(0, 0.9, n))

    for i, (result, label) in enumerate(zip(results, labels)):
        t, P, Q = _steady_state_slice(result, n_cycles=3)
        summary = result.summary()
        colour = colours[i]

        ax1 = axes[0, i]
        ax1.plot(t, P, color=colour, linewidth=2)
        ax1.axhline(summary["systolic_pressure_mmHg"], color="crimson",
                    linestyle="--", alpha=0.7, linewidth=1)
        ax1.axhline(summary["diastolic_pressure_mmHg"], color="seagreen",
                    linestyle="--", alpha=0.7, linewidth=1)
        ax1.set_title(
            f"{label}\n"
            f"{summary['systolic_pressure_mmHg']}/{summary['diastolic_pressure_mmHg']} mmHg",
            fontsize=9, fontweight="bold",
        )
        if i == 0:
            ax1.set_ylabel("Pressure (mmHg)", fontsize=11)
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(bottom=0)

        ax2 = axes[1, i]
        ax2.plot(t, Q, color=colour, linewidth=2)
        ax2.fill_between(t, Q, alpha=0.25, color=colour)
        ax2.set_title(
            f"CO: {summary['cardiac_output_L_per_min']} L/min  |  "
            f"HR: {summary['heart_rate_bpm']} bpm",
            fontsize=8,
        )
        if i == 0:
            ax2.set_ylabel("Flow (mL/s)", fontsize=11)
        ax2.set_xlabel("Time (s)", fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(bottom=-5)

    fig.suptitle(
        "Cardiovascular Digital Twin — Scenario Comparison",
        fontsize=14, fontweight="bold",
    )
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_pv_loop(
    system: "CardiovascularSystem",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Plot an idealised left-ventricular pressure–volume (PV) loop.

    The loop is constructed analytically from the heart and vasculature
    parameters using a simplified four-phase model:

    1. **Isovolumetric contraction** – volume constant at EDV, pressure
       rises from end-diastolic filling pressure to aortic diastolic BP.
    2. **Ejection** – volume decreases from EDV to ESV while pressure
       follows an arc peaking at systolic BP.
    3. **Isovolumetric relaxation** – volume constant at ESV, pressure
       falls back to the mitral opening threshold (~10 mmHg).
    4. **Filling (diastole)** – volume increases from ESV to EDV at low
       filling pressures (exponential stiffening).

    Parameters
    ----------
    system : CardiovascularSystem
        The cardiovascular system whose PV loop is to be plotted.
    save_path : str, optional
        If given, the figure is saved to this file path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    heart = system.heart
    EDV = heart.end_diastolic_volume
    ESV = heart.end_systolic_volume
    SV = heart.stroke_volume
    EF = heart.ejection_fraction

    # Estimated pressures from Windkessel equilibrium (proxy)
    # Use a rough heuristic: systolic ≈ R · peak_flow + venous_pressure + offset
    P_diastolic_approx = system.vasculature.venous_pressure + 75.0
    P_systolic_approx = P_diastolic_approx + SV / system.vasculature.compliance
    P_filling = system.vasculature.venous_pressure + 2.0   # end-diastolic filling P
    P_mitral_open = 10.0  # pressure at which mitral valve opens

    N = 200

    # Phase 1: isovolumetric contraction  (V = EDV, P rises)
    V1 = np.full(N, EDV)
    P1 = np.linspace(P_filling, P_diastolic_approx, N)

    # Phase 2: ejection  (V: EDV→ESV, P: arc peaking at systolic)
    frac = np.linspace(0, 1, N)
    V2 = EDV - SV * frac
    # Pressure arc: rises to systolic then falls back to diastolic
    P2 = P_diastolic_approx + (P_systolic_approx - P_diastolic_approx) * np.sin(np.pi * frac)

    # Phase 3: isovolumetric relaxation  (V = ESV, P falls)
    V3 = np.full(N, ESV)
    P3 = np.linspace(P_diastolic_approx, P_mitral_open, N)

    # Phase 4: diastolic filling  (V: ESV→EDV, P: exponential stiffening)
    frac4 = np.linspace(0, 1, N)
    V4 = ESV + SV * frac4
    P4 = P_mitral_open + (P_filling - P_mitral_open) * frac4 ** 2

    V_loop = np.concatenate([V1, V2, V3, V4])
    P_loop = np.concatenate([P1, P2, P3, P4])

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(V_loop, P_loop, color="#1f77b4", linewidth=2.5, label="PV loop")

    # Mark key points
    ax.plot(EDV, P_filling, "go", markersize=9, label=f"EDV = {EDV} mL")
    ax.plot(ESV, P_diastolic_approx, "rs", markersize=9, label=f"ESV = {ESV} mL")
    ax.annotate("EDV", (EDV, P_filling), textcoords="offset points",
                xytext=(8, -12), fontsize=9)
    ax.annotate("ESV", (ESV, P_diastolic_approx), textcoords="offset points",
                xytext=(-30, 6), fontsize=9)
    ax.annotate("Systole\n(ejection)", (np.mean(V2), np.max(P2)),
                textcoords="offset points", xytext=(10, 5), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="grey"))

    ax.set_xlabel("Left Ventricular Volume (mL)", fontsize=12)
    ax.set_ylabel("Left Ventricular Pressure (mmHg)", fontsize=12)
    ax.set_title(
        f"Pressure–Volume Loop — {system.scenario_description}",
        fontsize=13, fontweight="bold",
    )
    info = (
        f"SV: {SV} mL\n"
        f"EF: {EF:.0%}\n"
        f"HR: {heart.heart_rate} bpm\n"
        f"CO: {heart.cardiac_output:.1f} L/min"
    )
    ax.text(
        0.03, 0.97, info, transform=ax.transAxes,
        fontsize=10, verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.6),
    )
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig
