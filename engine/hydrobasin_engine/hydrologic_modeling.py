from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt


def _tr_key(value: float | int) -> str:
    return f"Tr_{float(value):g}"


def _effective_precipitation_scs(total_mm: float, cn: float) -> tuple[float, float, float]:
    s_mm = (25400.0 / cn) - 254.0
    ia_mm = 0.2 * s_mm
    if total_mm <= ia_mm:
        return 0.0, s_mm, ia_mm
    pe_mm = ((total_mm - ia_mm) ** 2) / (total_mm + 0.8 * s_mm)
    return pe_mm, s_mm, ia_mm


def compute_peak_discharges(
    area_km2: float,
    tc_hours: float,
    cn_weighted: float | None,
    design_intensities: dict[str, float] | None,
    return_periods: list[float | int],
    runoff_coefficient: float | None = None,
    design_precipitation_mm: dict[str, float] | None = None,
    design_flow_strategy: str | None = None,
    manual_design_flows: dict[str, float] | None = None,
    output_fig_path: Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Calcula caudales pico sin inventar parámetros faltantes.

    - Método racional: requiere intensidad de diseño y coeficiente C suministrado.
    - SCS: requiere CN y precipitación total de diseño por período de retorno.
    - El caudal adoptado solo se calcula cuando el usuario define una estrategia.

    No se estima C a partir del CN, no se insertan intensidades de respaldo y no se
    aplica una regla oculta para escoger Q de diseño.
    """
    area = float(area_km2)
    tc = float(tc_hours)
    if area <= 0 or tc <= 0:
        raise ValueError("Área y tiempo de concentración deben ser mayores que cero.")

    periods = [float(v) for v in return_periods]
    if not periods:
        return {
            "status": "unavailable",
            "reason": "No se suministraron períodos de retorno.",
            "results_by_return_period": [],
            "hydrographs": {},
        }, None

    if runoff_coefficient is not None:
        runoff_coefficient = float(runoff_coefficient)
        if not 0 < runoff_coefficient <= 1:
            raise ValueError("El coeficiente de escorrentía C debe estar entre 0 y 1.")

    if cn_weighted is not None:
        cn_weighted = float(cn_weighted)
        if not 0 < cn_weighted <= 100:
            raise ValueError("El CN ponderado debe estar entre 0 y 100.")

    valid_strategies = {None, "scs", "rational", "maximum", "minimum", "manual"}
    if design_flow_strategy not in valid_strategies:
        raise ValueError("Estrategia de Q adoptado no válida.")

    intensities = design_intensities or {}
    precipitations = design_precipitation_mm or {}
    manual = manual_design_flows or {}
    results: list[dict[str, Any]] = []

    for tr in periods:
        key = _tr_key(tr)
        intensity = intensities.get(key)
        precipitation = precipitations.get(key)

        q_rational = None
        if intensity is not None and runoff_coefficient is not None:
            intensity_value = float(intensity)
            if intensity_value < 0:
                raise ValueError(f"La intensidad para {key} no puede ser negativa.")
            q_rational = runoff_coefficient * intensity_value * area / 3.6

        q_scs = None
        pe_mm = None
        s_mm = None
        ia_mm = None
        if precipitation is not None and cn_weighted is not None:
            p_total = float(precipitation)
            if p_total < 0:
                raise ValueError(f"La precipitación total para {key} no puede ser negativa.")
            pe_mm, s_mm, ia_mm = _effective_precipitation_scs(p_total, cn_weighted)
            lag_h = 0.6 * tc
            tp_h = max(1e-9, lag_h)
            q_scs = (0.208 * area * pe_mm) / tp_h

        q_design = None
        if design_flow_strategy == "rational":
            q_design = q_rational
        elif design_flow_strategy == "scs":
            q_design = q_scs
        elif design_flow_strategy == "maximum":
            available = [q for q in (q_rational, q_scs) if q is not None]
            q_design = max(available) if available else None
        elif design_flow_strategy == "minimum":
            available = [q for q in (q_rational, q_scs) if q is not None]
            q_design = min(available) if available else None
        elif design_flow_strategy == "manual":
            raw_manual = manual.get(key)
            q_design = float(raw_manual) if raw_manual is not None else None

        results.append({
            "tr_anos": tr,
            "intensidad_mm_h": round(float(intensity), 4) if intensity is not None else None,
            "precipitacion_total_mm": round(float(precipitation), 4) if precipitation is not None else None,
            "precipitacion_efectiva_mm": round(pe_mm, 4) if pe_mm is not None else None,
            "retencion_s_mm": round(s_mm, 4) if s_mm is not None else None,
            "abstraccion_inicial_mm": round(ia_mm, 4) if ia_mm is not None else None,
            "caudal_racional_m3_s": round(q_rational, 4) if q_rational is not None else None,
            "caudal_scs_m3_s": round(q_scs, 4) if q_scs is not None else None,
            "caudal_diseno_m3_s": round(q_design, 4) if q_design is not None else None,
        })

    fig_str = None
    if output_fig_path and any(row.get("caudal_diseno_m3_s") is not None for row in results):
        try:
            labels = [f"Tr {row['tr_anos']:g}" for row in results if row.get("caudal_diseno_m3_s") is not None]
            values = [row["caudal_diseno_m3_s"] for row in results if row.get("caudal_diseno_m3_s") is not None]
            fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=200)
            ax.bar(labels, values)
            ax.set_title("Caudales pico adoptados por período de retorno", fontsize=10.5, fontweight="bold")
            ax.set_ylabel("Caudal (m³/s)")
            ax.grid(True, axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_fig_path, dpi=200, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            fig_str = str(output_fig_path)
        except Exception:
            fig_str = None

    return {
        "status": "ok",
        "results_by_return_period": results,
        "hydrographs": {},
        "runoff_coefficient_c": runoff_coefficient,
        "design_flow_strategy": design_flow_strategy,
        "note": "No se generan hidrogramas sintéticos sin un hietograma/modelo temporal explícito.",
    }, fig_str
