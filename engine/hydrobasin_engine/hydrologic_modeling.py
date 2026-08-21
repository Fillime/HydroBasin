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
    """Calcula los caudales pico de diseño por el Método Racional y el Hidrograma Unitario del SCS.
    Genera curvas continuas realistas basadas en la función Gamma del Hidrograma Adimensional del SCS (USDA-NRCS).
    """
    area = max(0.01, float(area_km2))
    tc = max(0.05, float(tc_hours))
    cn = max(40.0, min(98.0, float(cn_weighted)))

    # Parámetro de retención SCS S [mm]
    s_mm = (25400.0 / cn) - 254.0
    ia_mm = 0.2 * s_mm

    # Coeficiente de escorrentía Racional C (estimado a partir del CN)
    c_rational = round(min(0.95, max(0.15, (cn - 45.0) / 55.0 * 0.70 + 0.15)), 2)

    # Tiempo al pico SCS tp [horas]
    # En hidrología SCS, tp = D/2 + tl = 0.6 * Tc
    tp_hours = max(0.05, 0.6 * tc)
    # Tiempo base aproximado tb = 4.5 a 5.0 * tp para la función curvilínea completa
    tb_hours = max(1.0, 4.5 * tp_hours)

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

    # Vector de tiempo continuo de alta densidad (120 pasos) para curvas suaves y realistas
    t_arr = np.linspace(0, tb_hours, 120)
    # Factor de forma Gamma adimensional del SCS (m = 3.5 ajusta la curvatura del hidrograma SCS)
    m_shape = 3.5

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

        # Hidrograma Sintético Adimensional Curvilíneo del SCS:
        # q(t) = Qp * (t / tp)^m * exp(m * (1 - t / tp))
        ratio = np.maximum(1e-6, t_arr / tp_hours)
        q_curve = q_diseno * (ratio ** m_shape) * np.exp(m_shape * (1.0 - ratio))
        q_curve[0] = 0.0  # Comienzo suave en cero
        # Asegurar no negatividad y redondeo
        q_arr = [round(max(0.0, float(val)), 2) for val in q_curve]

        hydrographs[f"Tr_{tr_val}"] = {
            "time_hours": [round(float(t), 2) for t in t_arr],
            "time_minutes": [round(float(t * 60.0), 1) for t in t_arr],
            "flow_m3_s": q_arr,
        }

    fig_str = None
    if output_fig_path:
        try:
            fig, ax = plt.subplots(figsize=(9.2, 5.8), dpi=220)
            fig.patch.set_facecolor("#ffffff")
            ax.set_facecolor("#f8fafc")

            colors = ["#38bdf8", "#0284c7", "#16a34a", "#eab308", "#f97316", "#dc2626"]
            for i, (tr_key, tr_val) in enumerate(return_periods):
                h_data = hydrographs[f"Tr_{tr_val}"]
                c = colors[i % len(colors)]
                ax.plot(
                    h_data["time_hours"],
                    h_data["flow_m3_s"],
                    label=f"Tr = {tr_val} años (Qp = {results_tr[i]['caudal_diseno_m3_s']:,.2f} m³/s)",
                    color=c,
                    linewidth=2.2,
                )

            ax.set_title("Hidrogramas de Caudal de Diseño para Diferentes Periodos de Retorno (SCS Sintético)", fontsize=11.5, fontweight="bold", pad=12)
            ax.set_xlabel("Tiempo transcurrido desde el inicio de la tormenta (horas)", fontsize=9.5, labelpad=8)
            ax.set_ylabel("Caudal de Escorrentía Directa Q(t) (m³/s)", fontsize=9.5, labelpad=8)
            ax.grid(True, color="#cbd5e1", linestyle="--", linewidth=0.6, alpha=0.75)
            ax.tick_params(labelsize=8.5)
            ax.set_xlim(0, float(tb_hours))
            ax.set_ylim(bottom=0)
            ax.legend(loc="upper right", fontsize=8.5, framealpha=0.96, shadow=True)

            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_fig_path, dpi=220, bbox_inches="tight", facecolor="white")
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
