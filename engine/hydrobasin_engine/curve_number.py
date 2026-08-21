from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt


def compute_curve_number(
    total_area_km2: float,
    units: list[dict[str, Any]] | None = None,
    cn_weighted: float | None = None,
    output_fig_path: Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Calcula el Número de Curva SCS únicamente con datos suministrados.

    Se admite:
    - una lista de unidades homogéneas con ``cn`` y ``area_km2``; o
    - un CN ponderado previamente calculado/documentado.

    HydroBasin no genera coberturas, grupos hidrológicos, porcentajes ni valores CN
    sintéticos cuando no existen datos de entrada.
    """
    area = float(total_area_km2)
    if area <= 0:
        raise ValueError("El área total de la cuenca debe ser mayor que cero.")

    normalized_units: list[dict[str, Any]] = []

    if units:
        weighted_sum = 0.0
        area_sum = 0.0
        for index, raw in enumerate(units, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"La unidad CN #{index} debe ser un objeto.")
            if raw.get("cn") is None or raw.get("area_km2") is None:
                raise ValueError(f"La unidad CN #{index} requiere cn y area_km2.")

            cn = float(raw["cn"])
            unit_area = float(raw["area_km2"])
            if not 0 < cn <= 100:
                raise ValueError(f"El CN de la unidad #{index} debe estar entre 0 y 100.")
            if unit_area <= 0:
                raise ValueError(f"El área de la unidad CN #{index} debe ser mayor que cero.")

            weighted_sum += cn * unit_area
            area_sum += unit_area
            normalized_units.append({
                "cobertura": raw.get("cobertura"),
                "uso_scs": raw.get("uso_scs"),
                "condicion": raw.get("condicion"),
                "grupo_suelo": raw.get("grupo_suelo"),
                "cn": round(cn, 3),
                "area_km2": round(unit_area, 6),
                "nc_ai": round(cn * unit_area, 6),
                "source": raw.get("source"),
            })

        if area_sum <= 0:
            raise ValueError("La suma de áreas de las unidades CN debe ser mayor que cero.")
        cn_value = weighted_sum / area_sum
        area_used = area_sum
        source_mode = "weighted_units"
    elif cn_weighted is not None:
        cn_value = float(cn_weighted)
        if not 0 < cn_value <= 100:
            raise ValueError("El CN ponderado debe estar entre 0 y 100.")
        area_used = area
        source_mode = "provided_weighted_cn"
    else:
        return {
            "status": "unavailable",
            "reason": "No se suministraron unidades CN ni un CN ponderado documentado.",
            "units": [],
            "cn_weighted": None,
            "s_retention_mm": None,
            "ia_abstraction_mm": None,
            "area_used_km2": None,
            "source_mode": None,
        }, None

    s_retention_mm = (25400.0 / cn_value) - 254.0
    ia_mm = 0.2 * s_retention_mm

    fig_str = None
    if output_fig_path and normalized_units:
        try:
            fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=200)
            labels = [
                u.get("cobertura") or u.get("uso_scs") or f"Unidad {i + 1}"
                for i, u in enumerate(normalized_units)
            ]
            areas = [u["area_km2"] for u in normalized_units]
            cns = [u["cn"] for u in normalized_units]
            bars = ax.barh(labels, areas)
            for bar, cn_val in zip(bars, cns):
                width = bar.get_width()
                ax.text(width, bar.get_y() + bar.get_height() / 2.0, f" CN={cn_val:g}", va="center", fontsize=8)
            ax.set_title(f"Unidades de Número de Curva SCS (CN ponderado = {cn_value:.2f})", fontsize=10, fontweight="bold")
            ax.set_xlabel("Área (km²)", fontsize=8.5)
            ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
            ax.tick_params(labelsize=8)
            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_fig_path, dpi=200, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            fig_str = str(output_fig_path)
        except Exception:
            fig_str = None

    return {
        "status": "ok",
        "units": normalized_units,
        "cn_weighted": round(cn_value, 3),
        "s_retention_mm": round(s_retention_mm, 3),
        "ia_abstraction_mm": round(ia_mm, 3),
        "area_used_km2": round(area_used, 6),
        "source_mode": source_mode,
    }, fig_str
