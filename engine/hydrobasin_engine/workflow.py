from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .dem import cargar_dem, corregir_dem, metadatos_dem
from .delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto
from .hydrology import acumulacion_flujo, direccion_flujo
from .io import guardar_raster, guardar_vector, mascara_a_poligono
from .morphometry import parametros_morfometricos
from .streams import extraer_red_vectorial

ProgressCallback = Callable[[str, str, int], None]


def _geojson_web(gdf) -> dict:
    """Convierte un GeoDataFrame a GeoJSON EPSG:4326 listo para Leaflet."""
    if gdf is None or gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    web = gdf.to_crs("EPSG:4326")
    return json.loads(web.to_json())


def run_watershed_analysis(
    dem_path: str | Path,
    x: float,
    y: float,
    point_crs: str = "EPSG:4326",
    output_dir: str | Path = "results",
    drainage_threshold: float = 1000,
    snap_threshold: float | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    def report(level: str, message: str, percent: int) -> None:
        if progress:
            progress(level, message, percent)

    dem_path = Path(dem_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report("info", "Leyendo metadatos del modelo digital de elevación…", 3)
    metadata = metadatos_dem(dem_path)
    if not metadata["crs"]:
        raise ValueError("El DEM debe tener un sistema de referencia (CRS) definido.")
    report("ok", f"DEM válido · {metadata['width']} × {metadata['height']} celdas · {metadata['crs']}", 7)

    report("info", "Cargando el DEM en el motor hidrológico…", 10)
    grid, dem = cargar_dem(dem_path)
    report("ok", "DEM cargado correctamente.", 14)

    report("info", "Corrigiendo pits, depresiones y zonas planas del DEM…", 18)
    corrected_dem = corregir_dem(grid, dem)
    report("ok", "Corrección hidrológica del DEM completada.", 30)

    report("info", "Calculando la dirección de flujo mediante el método D8…", 34)
    flow_direction = direccion_flujo(grid, corrected_dem)
    report("ok", "Dirección de flujo calculada.", 43)

    report("info", "Calculando la acumulación de flujo en cada celda…", 47)
    accumulation = acumulacion_flujo(grid, flow_direction)
    report("ok", "Acumulación de flujo calculada.", 57)

    report("info", "Transformando el exutorio al sistema de referencia del DEM…", 60)
    x_dem, y_dem = transformar_punto(x, y, point_crs, metadata["crs"])
    minimum_accumulation = snap_threshold or drainage_threshold
    report("info", "Ajustando el exutorio a una celda de drenaje cercana…", 64)
    x_snap, y_snap = ajustar_punto_salida(grid, accumulation, x_dem, y_dem, minimum_accumulation)
    report("ok", "Exutorio ajustado a la red de flujo.", 69)

    report("info", "Delimitando todas las celdas que aportan al exutorio…", 72)
    watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)
    report("ok", "Máscara de cuenca delimitada.", 78)

    report("info", "Guardando rásteres intermedios del análisis…", 80)
    guardar_raster(output_dir / "dem_corregido.tif", corrected_dem, dem_path)
    guardar_raster(output_dir / "direccion_flujo.tif", flow_direction, dem_path)
    guardar_raster(output_dir / "acumulacion_flujo.tif", accumulation, dem_path)
    guardar_raster(output_dir / "cuenca_mask.tif", watershed_mask.astype("uint8"), dem_path, nodata=0)

    report("info", "Vectorizando el límite de la cuenca…", 84)
    watershed = mascara_a_poligono(watershed_mask, dem_path)
    guardar_vector(watershed, output_dir / "cuenca.gpkg")
    report("ok", "Polígono de cuenca generado.", 88)

    report("info", f"Extrayendo la red de drenaje con umbral de {drainage_threshold:,.0f} celdas…", 90)
    drainage = extraer_red_vectorial(
        grid,
        flow_direction,
        accumulation,
        drainage_threshold,
        crs=metadata["crs"],
    )
    if not drainage.empty:
        guardar_vector(drainage, output_dir / "red_drenaje.gpkg")
        report("ok", f"Red de drenaje generada · {len(drainage)} segmentos.", 94)
    else:
        report("warning", "No se generaron segmentos de drenaje con el umbral actual.", 94)

    report("info", "Calculando parámetros morfométricos de la cuenca…", 96)
    metrics = parametros_morfometricos(watershed)
    summary = {
        "crs_dem": metadata["crs"],
        "dem_width": metadata["width"],
        "dem_height": metadata["height"],
        "dem_resolution": [float(metadata["resolution"][0]), float(metadata["resolution"][1])],
        "outlet_original": {"x": x, "y": y, "crs": point_crs},
        "outlet_snapped": {"x": x_snap, "y": y_snap, "crs": metadata["crs"]},
        "drainage_threshold": drainage_threshold,
        **metrics,
    }

    result = {
        "summary": summary,
        "watershed_geojson": _geojson_web(watershed),
        "drainage_geojson": _geojson_web(drainage),
    }
    (output_dir / "resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report("ok", "Análisis completado. Resultados listos para visualizar.", 100)
    return result
