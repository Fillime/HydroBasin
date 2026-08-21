from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np


def _tr_key(value: float | int) -> str:
    number = float(value)
    return f"Tr_{number:g}"


def compute_idf_curves(
    tc_minutes: float,
    station_name: str = "Estación Base",
    output_fig_path: Path | None = None,
    return_periods: list[float | int] | None = None,
    parameters: dict[str, float] | None = None,
    durations_min: list[float | int] | None = None,
    curves_mm_h: dict[str, list[float]] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Calcula/interpreta curvas IDF exclusivamente con datos de entrada.

    Modos soportados:
    1) ``parameters`` con a, b, c, k para I=a*Tr^b/(d+c)^k.
    2) ``curves_mm_h`` con intensidades explícitas para cada duración y Tr.

    No se aplican coeficientes regionales predeterminados ni intensidades de respaldo.
    """
    tc = float(tc_minutes)
    if tc <= 0:
        raise ValueError("El tiempo de concentración debe ser mayor que cero.")

    periods = [float(v) for v in (return_periods or [])]
    if not periods:
        return {
            "status": "unavailable",
            "reason": "No se suministraron períodos de retorno para las curvas IDF.",
            "durations_min": [],
            "curves_mm_h": {},
            "design_intensities_mm_h": {},
            "tc_used_min": tc,
            "parameters": None,
            "source_mode": None,
        }, None

    durations = [float(v) for v in (durations_min or [tc])]
    if any(v <= 0 for v in durations):
        raise ValueError("Todas las duraciones IDF deben ser mayores que cero.")
    durations = sorted(set(durations))

    computed_curves: dict[str, list[float]] = {}
    design_intensities: dict[str, float] = {}
    source_mode: str | None = None
    used_parameters: dict[str, float] | None = None

    if parameters is not None:
        required = ("a", "b", "c", "k")
        missing = [key for key in required if parameters.get(key) is None]
        if missing:
            raise ValueError(f"Faltan parámetros IDF: {', '.join(missing)}.")
        a = float(parameters["a"])
        b = float(parameters["b"])
        c = float(parameters["c"])
        k = float(parameters["k"])
        if a <= 0 or k <= 0:
            raise ValueError("Los parámetros IDF a y k deben ser mayores que cero.")
        if any(d + c <= 0 for d in durations + [tc]):
            raise ValueError("El parámetro c produce una duración efectiva no válida.")

        used_parameters = {"a": a, "b": b, "c": c, "k": k}
        source_mode = "parameters"
        for tr in periods:
            key = _tr_key(tr)
            values = [(a * (tr ** b)) / ((d + c) ** k) for d in durations]
            computed_curves[key] = [round(float(v), 4) for v in values]
            design_intensities[key] = round(float((a * (tr ** b)) / ((tc + c) ** k)), 4)

    elif curves_mm_h is not None:
        if len(durations) < 1:
            raise ValueError("Se requieren duraciones para interpretar curvas IDF explícitas.")
        source_mode = "explicit_curves"
        for tr in periods:
            key = _tr_key(tr)
            values = curves_mm_h.get(key)
            if values is None:
                raise ValueError(f"No existe curva IDF para {key}.")
            if len(values) != len(durations):
                raise ValueError(f"La curva {key} debe tener {len(durations)} valores.")
            numeric = [float(v) for v in values]
            if any(v < 0 for v in numeric):
                raise ValueError(f"La curva {key} contiene intensidades negativas.")
            computed_curves[key] = [round(v, 4) for v in numeric]
            design_intensities[key] = round(float(np.interp(tc, durations, numeric)), 4)
    else:
        return {
            "status": "unavailable",
            "reason": "No se suministraron parámetros ni curvas IDF observadas/ajustadas.",
            "durations_min": durations,
            "curves_mm_h": {},
            "design_intensities_mm_h": {},
            "tc_used_min": tc,
            "parameters": None,
            "source_mode": None,
        }, None

    fig_str = None
    if output_fig_path:
        try:
            fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=200)
            for tr in periods:
                key = _tr_key(tr)
                ax.plot(durations, computed_curves[key], label=f"Tr = {tr:g} años", linewidth=1.8)
            ax.axvline(tc, linestyle="--", linewidth=1.2, label=f"Tc = {tc:.1f} min")
            ax.set_title(f"Curvas Intensidad–Duración–Frecuencia (IDF) — {station_name}", fontsize=10.5, fontweight="bold")
            ax.set_xlabel("Duración de la lluvia (min)", fontsize=8.5)
            ax.set_ylabel("Intensidad (mm/h)", fontsize=8.5)
            ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
            ax.tick_params(labelsize=8)
            ax.legend(loc="best", fontsize=7.5, framealpha=0.95)
            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_fig_path, dpi=200, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            fig_str = str(output_fig_path)
        except Exception:
            fig_str = None

    return {
        "status": "ok",
        "durations_min": [round(v, 4) for v in durations],
        "curves_mm_h": computed_curves,
        "design_intensities_mm_h": design_intensities,
        "tc_used_min": round(tc, 4),
        "parameters": used_parameters,
        "source_mode": source_mode,
    }, fig_str
