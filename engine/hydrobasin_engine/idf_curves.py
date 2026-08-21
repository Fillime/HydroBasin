from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np


def compute_idf_curves(
    tc_minutes: float,
    station_name: str = "Estación Base",
    output_fig_path: Path | None = None,
    return_periods: list[int] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Calcula las curvas Intensidad-Duración-Frecuencia (IDF) y la intensidad de diseño para el Tc."""
    if return_periods is None:
        return_periods = [2.33, 5, 10, 25, 50, 100]

    # Parámetros representativos de curvas IDF en Colombia (Vargas & Díaz / IDEAM)
    # I = a * Tr^b / (d + c)^k  [mm/h], d en minutos
    a_param = 1150.0
    b_param = 0.22
    c_param = 14.5
    k_param = 0.82

    durations = np.array([5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360, 720, 1440], dtype=float)

    curves: dict[str, list[float]] = {}
    design_intensities: dict[str, float] = {}

    d_tc = max(5.0, min(1440.0, tc_minutes))

    for tr in return_periods:
        tr_key = f"Tr_{tr}" if isinstance(tr, int) else f"Tr_{tr:g}"
        intensities = (a_param * (tr ** b_param)) / ((durations + c_param) ** k_param)
        curves[tr_key] = [round(float(v), 2) for v in intensities]

        # Intensidad exactamente en la duración Tc
        i_tc = (a_param * (tr ** b_param)) / ((d_tc + c_param) ** k_param)
        design_intensities[tr_key] = round(float(i_tc), 2)

    fig_str = None
    if output_fig_path:
        try:
            fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=200)
            fig.patch.set_facecolor("#ffffff")
            ax.set_facecolor("#f8fafc")

            colors = ["#38bdf8", "#0284c7", "#16a34a", "#eab308", "#f97316", "#dc2626"]
            for i, tr in enumerate(return_periods):
                tr_key = f"Tr_{tr}" if isinstance(tr, int) else f"Tr_{tr:g}"
                c = colors[i % len(colors)]
                ax.plot(durations, curves[tr_key], label=f"Tr = {tr} años", color=c, linewidth=1.8)

            # Línea vertical del Tc
            ax.axvline(d_tc, color="#64748b", linestyle="--", linewidth=1.2, label=f"Tc = {d_tc:.1f} min")

            ax.set_title(f"Curvas Intensidad -- Duración -- Frecuencia (IDF) -- {station_name}", fontsize=10.5, fontweight="bold")
            ax.set_xlabel("Duración de la Lluvia (minutos)", fontsize=8.5)
            ax.set_ylabel("Intensidad de Precipitación (mm/h)", fontsize=8.5)
            ax.set_xlim(0, 360)
            ax.grid(True, color="#cbd5e1", linestyle="--", linewidth=0.5, alpha=0.7)
            ax.tick_params(labelsize=8)
            ax.legend(loc="upper right", fontsize=7.5, framealpha=0.95)

            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_fig_path, dpi=200, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            fig_str = str(output_fig_path)
        except Exception:
            pass

    return {
        "durations_min": [int(d) for d in durations],
        "curves_mm_h": curves,
        "design_intensities_mm_h": design_intensities,
        "tc_used_min": round(d_tc, 1),
        "parameters": {"a": a_param, "b": b_param, "c": c_param, "k": k_param},
    }, fig_str
