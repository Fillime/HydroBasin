from __future__ import annotations

import json
from pathlib import Path

from .dem import cargar_dem, corregir_dem, metadatos_dem
from .delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto
from .hydrology import acumulacion_flujo, direccion_flujo
from .io import guardar_raster, guardar_vector, mascara_a_poligono
from .morphometry import parametros_morfometricos
from .streams import extraer_red_vectorial


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
) -> dict:
    dem_path = Path(dem_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = metadatos_dem(dem_path)
    if not metadata["crs"]:
        raise ValueError("El DEM debe tener un sistema de referencia (CRS) definido.")

    grid, dem = cargar_dem(dem_path)
    corrected_dem = corregir_dem(grid, dem)
    flow_direction = direccion_flujo(grid, corrected_dem)
    accumulation = acumulacion_flujo(grid, flow_direction)

    x_dem, y_dem = transformar_punto(x, y, point_crs, metadata["crs"])
    minimum_accumulation = snap_threshold or drainage_threshold
    x_snap, y_snap = ajustar_punto_salida(grid, accumulation, x_dem, y_dem, minimum_accumulation)
    watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)

    guardar_raster(output_dir / "dem_corregido.tif", corrected_dem, dem_path)
    guardar_raster(output_dir / "direccion_flujo.tif", flow_direction, dem_path)
    guardar_raster(output_dir / "acumulacion_flujo.tif", accumulation, dem_path)
    guardar_raster(output_dir / "cuenca_mask.tif", watershed_mask.astype("uint8"), dem_path, nodata=0)

    watershed = mascara_a_poligono(watershed_mask, dem_path)
    guardar_vector(watershed, output_dir / "cuenca.gpkg")

    drainage = extraer_red_vectorial(
        grid,
        flow_direction,
        accumulation,
        drainage_threshold,
        crs=metadata["crs"],
    )
    if not drainage.empty:
        guardar_vector(drainage, output_dir / "red_drenaje.gpkg")

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
    return result
