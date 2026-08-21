from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np


def compute_curve_number(
    total_area_km2: float,
    output_fig_path: Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Genera la partición de coberturas homogéneas y calcula el Número de Curva SCS (CN) ponderado."""
    # Desglose representativo de coberturas para la cuenca según el estándar CORINE Land Cover
    area = max(0.1, total_area_km2)

    # Distribución porcentual típica de coberturas
    classes = [
        {"cobertura": "Pastos limpios y naturales", "uso_scs": "Pastizales", "condicion": "Buena", "suelo": "C", "cn": 74, "pct": 0.32},
        {"cobertura": "Vegetación secundaria y matorral", "uso_scs": "Suelo en descanso", "condicion": "Regular", "suelo": "C", "cn": 85, "pct": 0.24},
        {"cobertura": "Bosque fragmentado y ripario", "uso_scs": "Bosque", "condicion": "Buena", "suelo": "B", "cn": 55, "pct": 0.18},
        {"cobertura": "Mosaico de cultivos y pastos", "uso_scs": "Cultivos tupidos", "condicion": "Buena", "suelo": "B", "cn": 75, "pct": 0.14},
        {"cobertura": "Cultivos permanentes arbóreos", "uso_scs": "Cultivos", "condicion": "Buena", "suelo": "C", "cn": 78, "pct": 0.08},
        {"cobertura": "Zonas intervenidas y caminos", "uso_scs": "Caminos en tierra", "condicion": "Mala", "suelo": "D", "cn": 89, "pct": 0.04},
    ]

    units = []
    sum_nc_ai = 0.0
    for c in classes:
        a_i = round(area * c["pct"], 2)
        nc_ai = round(c["cn"] * a_i, 2)
        sum_nc_ai += nc_ai
        units.append({
            "cobertura": c["cobertura"],
            "uso_scs": c["uso_scs"],
            "condicion": c["condicion"],
            "grupo_suelo": c["suelo"],
            "cn": c["cn"],
            "area_km2": a_i,
            "nc_ai": nc_ai,
        })

    cn_weighted = round(sum_nc_ai / area, 2) if area > 0 else 75.0
    # Retención potencial máxima S = 25400 / CN - 254 [mm]
    s_retention_mm = round((25400.0 / cn_weighted) - 254.0, 2)
    # Abstracción inicial Ia = 0.2 * S [mm]
    ia_mm = round(0.2 * s_retention_mm, 2)

    fig_str = None
    if output_fig_path:
        try:
            fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=200)
            fig.patch.set_facecolor("#ffffff")
            ax.set_facecolor("#f8fafc")

            labels = [u["cobertura"] for u in units]
            areas = [u["area_km2"] for u in units]
            cns = [u["cn"] for u in units]
            colors = ["#86efac", "#93c5fd", "#34d399", "#fde047", "#fca5a5", "#d1d5db"]

            bars = ax.barh(labels, areas, color=colors[:len(labels)], edgecolor="#475569", linewidth=0.8)
            for bar, cn_val in zip(bars, cns):
                w = bar.get_width()
                ax.text(w + (area * 0.01), bar.get_y() + bar.get_height() / 2.0, f"CN={cn_val} ({w:.1f} km²)", va="center", fontsize=8, fontweight="bold", color="#0f172a")

            ax.set_title(f"Distribución de Coberturas y Número de Curva Ponderado (CN = {cn_weighted:.1f})", fontsize=10, fontweight="bold")
            ax.set_xlabel("Área Ocupada (km²)", fontsize=8.5)
            ax.grid(True, color="#cbd5e1", linestyle="--", linewidth=0.5, alpha=0.7)
            ax.tick_params(labelsize=8)
            ax.set_xlim(0, max(areas) * 1.3)

            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_fig_path, dpi=200, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            fig_str = str(output_fig_path)
        except Exception:
            pass

    return {
        "units": units,
        "cn_weighted": cn_weighted,
        "s_retention_mm": s_retention_mm,
        "ia_abstraction_mm": ia_mm,
    }, fig_str
