from __future__ import annotations

import json
from pathlib import Path

from pysheds.grid import Grid

from .delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto
from .dem import metadatos_dem
from .io import mascara_a_poligono
from .morphometry import parametros_morfometricos


def _geojson_web(gdf) -> dict:
    if gdf is None or gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(gdf.to_crs("EPSG:4326").to_json())


def recalculate_watershed_from_cache(
    results_dir: str | Path,
    x: float,
    y: float,
    point_crs: str = "EPSG:4326",
) -> dict:
    """Recalcula solo la cuenca para un nuevo exutorio reutilizando resultados pesados.

    Reutiliza el DEM corregido, la dirección de flujo y la acumulación ya calculadas
    durante un análisis completo. No vuelve a acondicionar el DEM, calcular D8,
    acumulación, Strahler, subcuencas, cauce principal ni generar informes.
    """
    results_dir = Path(results_dir)
    corrected_path = results_dir / "dem_corregido.tif"
    flow_path = results_dir / "direccion_flujo.tif"
    accumulation_path = results_dir / "acumulacion_flujo.tif"
    summary_path = results_dir / "resumen.json"

    missing = [p.name for p in (corrected_path, flow_path, accumulation_path, summary_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "El análisis base no tiene todos los archivos necesarios para el recálculo rápido: "
            + ", ".join(missing)
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata = metadatos_dem(corrected_path)
    grid = Grid.from_raster(str(corrected_path))
    flow_direction = grid.read_raster(str(flow_path))
    accumulation = grid.read_raster(str(accumulation_path))

    x_dem, y_dem = transformar_punto(x, y, point_crs, metadata["crs"])
    threshold = float(summary.get("drainage_threshold") or 1)
    x_snap, y_snap = ajustar_punto_salida(grid, accumulation, x_dem, y_dem, threshold)
    watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)
    watershed = mascara_a_poligono(watershed_mask, corrected_path)
    metrics = parametros_morfometricos(watershed, drainage=None)

    updated_summary = {
        **summary,
        "outlet_original": {"x": x, "y": y, "crs": point_crs},
        "outlet_snapped": {"x": x_snap, "y": y_snap, "crs": metadata["crs"]},
        "area_km2": metrics.get("area_km2"),
        "perimetro_km": metrics.get("perimetro_km"),
        "longitud_axial_km": metrics.get("longitud_axial_km"),
        "factor_forma": metrics.get("factor_forma"),
        "coeficiente_compacidad": metrics.get("coeficiente_compacidad"),
        "relacion_circularidad": metrics.get("relacion_circularidad"),
        "crs_calculo": metrics.get("crs_calculo"),
        "quick_recalculation": True,
    }

    return {
        "summary": updated_summary,
        "watershed_geojson": _geojson_web(watershed),
        "quick_recalculation": True,
        "reused": ["dem_corregido", "direccion_flujo", "acumulacion_flujo"],
    }
