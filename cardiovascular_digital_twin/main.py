"""
Cardiovascular Digital Twin
============================
Main entry point — simulates all predefined physiological scenarios,
prints a haemodynamic summary for each, and saves output plots.

Usage
-----
    cd cardiovascular_digital_twin
    python main.py
"""

import os
import sys

# Ensure the package root is importable when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cardiovascular_digital_twin.models.cardiovascular_system import (
    CardiovascularSystem,
    SCENARIOS,
)
from cardiovascular_digital_twin.simulation.simulator import Simulator
from cardiovascular_digital_twin.visualization.plotter import (
    plot_simulation,
    plot_comparison,
    plot_pv_loop,
)


def _banner(text: str, width: int = 60) -> None:
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def run_scenario(scenario_name: str, output_dir: str) -> "SimulationResult":
    """Run a single named scenario, print summary, save plots."""
    system = CardiovascularSystem.from_scenario(scenario_name)
    simulator = Simulator(system)
    result = simulator.run(n_cycles=15)

    _banner(f"{scenario_name.upper()}  —  {system.scenario_description}")
    print(f"\n  {'Metric':<40} {'Value'}")
    print(f"  {'-'*50}")
    for key, value in result.summary().items():
        print(f"  {key.replace('_', ' ').title():<40} {value}")

    # Time-series plot
    ts_path = os.path.join(output_dir, f"{scenario_name}_timeseries.png")
    plot_simulation(result, save_path=ts_path)

    # PV loop
    pv_path = os.path.join(output_dir, f"{scenario_name}_pv_loop.png")
    plot_pv_loop(system, save_path=pv_path)

    print(f"\n  Plots saved → {ts_path}")
    print(f"              → {pv_path}")
    return result


def main() -> None:
    """Run all scenarios and produce a comparison figure."""
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║       CARDIOVASCULAR SYSTEM — DIGITAL TWIN               ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(
        "\nSimulating the cardiovascular system using a two-element\n"
        "Windkessel model across 6 physiological scenarios.\n"
    )

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    os.makedirs(output_dir, exist_ok=True)

    results = {}
    for name in SCENARIOS:
        results[name] = run_scenario(name, output_dir)

    # Comparison figure
    scenario_names = list(SCENARIOS.keys())
    comparison_path = os.path.join(output_dir, "comparison.png")
    plot_comparison(
        [results[n] for n in scenario_names],
        labels=scenario_names,
        save_path=comparison_path,
    )
    _banner("SIMULATION COMPLETE")
    print(f"\n  Comparison plot → {comparison_path}")
    print(f"\n  All outputs in  → {output_dir}/\n")


if __name__ == "__main__":
    main()
