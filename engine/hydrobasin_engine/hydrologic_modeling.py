from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np


def compute_peak_discharges(
    area_km2: float,
    tc_hours: float,
    cn_weighted: float,
    design_intensities: dict[str, float],
    output_fig_path: Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Calcula los caudales pico de diseño por el Método Racional y el Hidrograma Unitario del SCS."""
    area = max(0.01, area_km2)
    tc = max(0.05, tc_hours)
    cn = max(40.0, min(98.0, cn_weighted))

    # Parámetro de retención SCS S [mm]
    s_mm = (25400.0 / cn) - 254.0
    ia_mm = 0.2 * s_mm

    # Coeficiente de escorrentía Racional C (estimado a partir del CN)
    c_rational = round(min(0.95, max(0.15, (cn - 45.0) / 55.0 * 0.70 + 0.15)), 2)

    # Tiempo al pico SCS tp [horas]
    tp_hours = max(0.05, 0.6 * tc)
    tb_hours = 2.67 * tp_hours  # Tiempo base [horas]

    results_tr: list[dict[str, Any]] = []
    hydrographs: dict[str, dict[str, list[float]]] = {}

    return_periods = [
        ("Tr_2.33", 2.33),
        ("Tr_5", 5),
        ("Tr_10", 10),
        ("Tr_25", 25),
        ("Tr_50", 50),
        ("Tr_100", 100),
    ]

    for tr_key, tr_val in return_periods:
        i_mm_h = design_intensities.get(tr_key) or (design_intensities.get(f"Tr_{tr_val}") or 50.0)

        # 1. Método Racional: Q = (C * I * A) / 3.6  [m3/s]
        q_racional = (c_rational * i_mm_h * area) / 3.6

        # 2. Precipitación total acumulada en la duración Tc [mm]
        p_total_mm = i_mm_h * tc

        # Precipitación efectiva SCS Pe [mm]
        if p_total_mm > ia_mm:
            pe_mm = ((p_total_mm - ia_mm) ** 2) / (p_total_mm + 0.8 * s_mm)
        else:
            pe_mm = 0.0

        # Caudal pico SCS: Qp = (0.208 * A * Pe) / tp  [m3/s]
        q_scs = (0.208 * area * pe_mm) / tp_hours if tp_hours > 0 else q_racional

        # Caudal de diseño adoptado (promedio ponderado o valor conservador)
        q_diseno = round(max(q_racional * 0.9, q_scs), 2)

        results_tr.append({
            "tr_anos": tr_val,
            "intensidad_mm_h": round(i_mm_h, 2),
            "precipitacion_total_mm": round(p_total_mm, 2),
            "precipitacion_efectiva_mm": round(pe_mm, 2),
            "caudal_racional_m3_s": round(q_racional, 2),
            "caudal_scs_m3_s": round(q_scs, 2),
            "caudal_diseno_m3_s": q_diseno,
        })

        # Generar hidrograma sintético Q(t)
        t_arr = np.linspace(0, tb_hours * 1.6, 50)
        q_arr = []
        for t in t_arr:
            if t <= tp_hours:
                qt = q_diseno * (t / tp_hours)
            elif t <= tb_hours:
                qt = q_diseno * (1.0 - (t - tp_hours) / (tb_hours - tp_hours))
            else:
                qt = 0.0
            q_arr.append(round(max(0.0, float(qt)), 2))

        hydrographs[f"Tr_{tr_val}"] = {
            "time_hours": [round(float(t), 2) for t in t_arr],
            "time_minutes": [round(float(t * 60.0), 1) for t in t_arr],
            "flow_m3_s": q_arr,
        }

    fig_str = None
    if output_fig_path:
        try:
            fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=200)
            fig.patch.set_facecolor("#ffffff")
            ax.set_facecolor("#f8fafc")

            colors = ["#38bdf8", "#0284c7", "#16a34a", "#eab308", "#f97316", "#dc2626"]
            for i, (tr_key, tr_val) in enumerate(return_periods):
                h_data = hydrographs[f"Tr_{tr_val}"]
                c = colors[i % len(colors)]
                ax.plot(h_data["time_hours"], h_data["flow_m3_s"], label=f"Tr = {tr_val} años (Qp = {results_tr[i]['caudal_diseno_m3_s']} m³/s)", color=c, linewidth=1.8)

            ax.set_title("Hidrogramas de Caudal de Diseño para Diferentes Periodos de Retorno", fontsize=10.5, fontweight="bold")
            ax.set_xlabel("Tiempo (horas)", fontsize=8.5)
            ax.set_ylabel("Caudal de Escorrentía (m³/s)", fontsize=8.5)
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
        "results_by_return_period": results_tr,
        "hydrographs": hydrographs,
        "runoff_coefficient_c": c_rational,
        "time_to_peak_hours": round(tp_hours, 2),
        "base_time_hours": round(tb_hours, 2),
    }, fig_str
