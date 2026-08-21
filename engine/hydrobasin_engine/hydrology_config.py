from __future__ import annotations

from typing import Any


def normalize_return_periods(values: list[float | int] | None) -> list[float]:
    if not values:
        return []
    result: list[float] = []
    seen: set[float] = set()
    for raw in values:
        value = float(raw)
        if value <= 1.0:
            raise ValueError("Cada período de retorno debe ser mayor que 1 año.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return sorted(result)


def validate_hydrology_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Valida la configuración hidrológica suministrada por el usuario.

    HydroBasin no inventa estaciones, CN, curvas IDF, coeficientes de escorrentía
    ni criterios de adopción. Si un bloque de datos no está disponible, ese cálculo
    simplemente queda marcado como no disponible.
    """
    if not config:
        return {
            "enabled": False,
            "return_periods": [],
            "stations": [],
            "idf": None,
            "curve_number": None,
            "runoff_coefficient": None,
            "design_flow_strategy": None,
        }

    periods = normalize_return_periods(config.get("return_periods"))
    stations = config.get("stations") or []
    if not isinstance(stations, list):
        raise ValueError("hydrology_config.stations debe ser una lista.")

    idf = config.get("idf")
    if idf is not None and not isinstance(idf, dict):
        raise ValueError("hydrology_config.idf debe ser un objeto.")

    curve_number = config.get("curve_number")
    if curve_number is not None and not isinstance(curve_number, dict):
        raise ValueError("hydrology_config.curve_number debe ser un objeto.")

    runoff_coefficient = config.get("runoff_coefficient")
    if runoff_coefficient is not None:
        runoff_coefficient = float(runoff_coefficient)
        if not 0.0 < runoff_coefficient <= 1.0:
            raise ValueError("El coeficiente de escorrentía debe estar entre 0 y 1.")

    strategy = config.get("design_flow_strategy")
    valid_strategies = {None, "scs", "rational", "maximum", "minimum", "manual"}
    if strategy not in valid_strategies:
        raise ValueError(
            "design_flow_strategy debe ser scs, rational, maximum, minimum o manual."
        )

    return {
        "enabled": bool(config.get("enabled", True)),
        "return_periods": periods,
        "stations": stations,
        "idf": idf,
        "curve_number": curve_number,
        "runoff_coefficient": runoff_coefficient,
        "design_flow_strategy": strategy,
        "manual_design_flows": config.get("manual_design_flows") or {},
        "metadata": config.get("metadata") or {},
    }
