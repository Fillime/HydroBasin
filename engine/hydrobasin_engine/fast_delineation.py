from __future__ import annotations

import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from pysheds.grid import Grid
from rasterio.enums import Resampling

from .delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto
from .dem import metadatos_dem
from .io import guardar_raster, guardar_shapefile_zip, guardar_vector, mascara_a_poligono
from .main_channel import extraer_cauce_principal, tiempos_concentracion
from .morphometry import parametros_morfometricos
from .report import generar_figuras
from .report_professional import generar_informes
from .streams import extraer_red_vectorial
from .subbasins import delimitar_subcuencas


def _geojson_web(gdf) -> dict:
    if gdf is None or gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(gdf.to_crs("EPSG:4326").to_json())


def _masked_elevation_stats(values, mask, chunk_rows: int = 512) -> dict:
    array = np.asarray(values)
    mask_array = np.asarray(mask)
    minimum = np.inf
    maximum = -np.inf
    total = 0.0
    count = 0
    for start in range(0, array.shape[0], chunk_rows):
        stop = min(array.shape[0], start + chunk_rows)
        block = array[start:stop]
        block_mask = mask_array[start:stop].astype(bool, copy=False)
        selected = block[block_mask]
        if selected.size == 0:
            continue
        selected = selected[np.isfinite(selected)]
        if selected.size == 0:
            continue
        minimum = min(minimum, float(selected.min()))
        maximum = max(maximum, float(selected.max()))
        total += float(selected.sum(dtype="float64"))
        count += int(selected.size)
    if count == 0:
        return {
            "elevacion_min_m": None,
            "elevacion_max_m": None,
            "elevacion_media_m": None,
            "relieve_cuenca_m": None,
        }
    return {
        "elevacion_min_m": minimum,
        "elevacion_max_m": maximum,
        "elevacion_media_m": total / count,
        "relieve_cuenca_m": maximum - minimum,
    }


def _context_preview(path: Path, max_dim: int = 1400):
    with rasterio.open(path) as src:
        scale = min(1.0, max_dim / max(src.width, src.height))
        width = max(1, int(src.width * scale))
        height = max(1, int(src.height * scale))
        return src.read(1, out_shape=(height, width), resampling=Resampling.bilinear)


def _remove_if_exists(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def _cached_drainage(results_dir: Path, grid, flow_direction, accumulation, threshold: float, crs, watershed):
    """Conserva una copia de la red base y devuelve únicamente los tramos de la nueva cuenca."""
    current = results_dir / "red_drenaje.gpkg"
    cache = results_dir / "red_drenaje_cache.gpkg"
    if not cache.exists() and current.exists():
        shutil.copy2(current, cache)

    if cache.exists():
        base = gpd.read_file(cache)
    else:
        base = extraer_red_vectorial(grid, flow_direction, accumulation, threshold, crs=crs)
        if not base.empty:
            guardar_vector(base, cache)

    if base.empty:
        return base

    basin_geom = watershed.to_crs(base.crs) if watershed.crs != base.crs else watershed
    clipped = gpd.clip(base, basin_geom)
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
    if not clipped.empty:
        clipped = clipped.explode(index_parts=False, ignore_index=True)
    return clipped


def recalculate_watershed_from_cache(
    results_dir: str | Path,
    x: float,
    y: float,
    point_crs: str = "EPSG:4326",
) -> dict:
    """Actualiza un análisis cuando solo cambia el exutorio.

    Reutiliza las etapas costosas e invariantes del análisis: DEM corregido, dirección D8,
    acumulación y Strahler. A partir del nuevo punto vuelve a calcular todo lo que sí depende
    de la cuenca: divisoria, red recortada, morfometría, cauce principal, subcuencas,
    figuras, informe PDF y plano PDF.
    """
    results_dir = Path(results_dir)
    corrected_path = results_dir / "dem_corregido.tif"
    flow_path = results_dir / "direccion_flujo.tif"
    accumulation_path = results_dir / "acumulacion_flujo.tif"
    strahler_path = results_dir / "strahler.tif"
    summary_path = results_dir / "resumen.json"

    required = (corrected_path, flow_path, accumulation_path, strahler_path, summary_path)
    missing = [p.name for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "El análisis base no tiene todos los archivos necesarios para el recálculo rápido: "
            + ", ".join(missing)
        )

    previous_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata = metadatos_dem(corrected_path)
    grid = Grid.from_raster(str(corrected_path))
    corrected_dem = grid.read_raster(str(corrected_path))
    flow_direction = grid.read_raster(str(flow_path))
    accumulation = grid.read_raster(str(accumulation_path))
    strahler = grid.read_raster(str(strahler_path))

    threshold = float(previous_summary.get("drainage_threshold") or 1)
    x_dem, y_dem = transformar_punto(x, y, point_crs, metadata["crs"])
    x_snap, y_snap = ajustar_punto_salida(grid, accumulation, x_dem, y_dem, threshold)
    watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)
    watershed = mascara_a_poligono(watershed_mask, corrected_path)

    drainage = _cached_drainage(
        results_dir,
        grid,
        flow_direction,
        accumulation,
        threshold,
        metadata["crs"],
        watershed,
    )

    main_channel, channel_metrics = extraer_cauce_principal(
        flow_direction,
        accumulation,
        watershed_mask,
        corrected_dem,
        metadata["transform"],
        metadata["crs"],
        x_snap,
        y_snap,
    )

    subbasin_labels, subbasins = delimitar_subcuencas(
        flow_direction,
        accumulation,
        watershed_mask,
        metadata["transform"],
        metadata["crs"],
        threshold,
    )

    metrics = parametros_morfometricos(watershed, drainage=drainage)
    tc_metrics = tiempos_concentracion(
        channel_metrics.get("main_channel_length_km"),
        channel_metrics.get("main_channel_slope"),
    )
    relief_metrics = _masked_elevation_stats(corrected_dem, watershed_mask)

    updated_summary = {
        **previous_summary,
        "outlet_original": {"x": x, "y": y, "crs": point_crs},
        "outlet_snapped": {"x": x_snap, "y": y_snap, "crs": metadata["crs"]},
        "strahler_max": int(np.asarray(strahler)[np.asarray(watershed_mask, dtype=bool)].max()) if np.any(watershed_mask) else 0,
        "subbasin_count": int(len(subbasins)),
        "quick_recalculation": True,
        **metrics,
        **channel_metrics,
        **tc_metrics,
        **relief_metrics,
    }

    # Sobrescribir únicamente productos dependientes del exutorio. Los rasters base
    # (DEM corregido, D8, acumulación y Strahler) se mantienen intactos y reutilizables.
    guardar_vector(watershed, results_dir / "cuenca.gpkg")
    guardar_shapefile_zip(watershed, results_dir / "cuenca_shp.zip", "cuenca")
    guardar_raster(results_dir / "cuenca_mask.tif", np.asarray(watershed_mask).astype("uint8"), corrected_path, nodata=0)

    if not drainage.empty:
        guardar_vector(drainage, results_dir / "red_drenaje.gpkg")
        guardar_shapefile_zip(drainage, results_dir / "red_drenaje_shp.zip", "red_drenaje")
    else:
        _remove_if_exists(results_dir / "red_drenaje.gpkg", results_dir / "red_drenaje_shp.zip")

    if not main_channel.empty:
        guardar_vector(main_channel, results_dir / "cauce_principal.gpkg")
        guardar_shapefile_zip(main_channel, results_dir / "cauce_principal_shp.zip", "cauce_principal")
    else:
        _remove_if_exists(results_dir / "cauce_principal.gpkg", results_dir / "cauce_principal_shp.zip")

    guardar_raster(results_dir / "subcuencas.tif", np.asarray(subbasin_labels).astype("int32"), corrected_path, nodata=0)
    if not subbasins.empty:
        guardar_vector(subbasins, results_dir / "subcuencas.gpkg")
        guardar_shapefile_zip(subbasins, results_dir / "subcuencas_shp.zip", "subcuencas")
    else:
        _remove_if_exists(results_dir / "subcuencas.gpkg", results_dir / "subcuencas_shp.zip")

    dem_context = _context_preview(corrected_path)
    figures = generar_figuras(
        results_dir,
        grid,
        dem_context,
        corrected_dem,
        accumulation,
        watershed_mask,
        strahler,
        watershed,
        drainage,
        subbasins=subbasins,
        main_channel=main_channel,
        summary=updated_summary,
        flow_direction=flow_direction,
    )
    report_files = generar_informes(
        results_dir,
        updated_summary,
        figures,
        subbasins=subbasins,
        main_channel=main_channel,
    )

    summary_path.write_text(json.dumps(updated_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "summary": updated_summary,
        "watershed_geojson": _geojson_web(watershed),
        "drainage_geojson": _geojson_web(drainage),
        "subbasins_geojson": _geojson_web(subbasins),
        "main_channel_geojson": _geojson_web(main_channel),
        "figures": figures,
        "report": report_files,
        "quick_recalculation": True,
        "reused": ["dem_corregido", "direccion_flujo", "acumulacion_flujo", "strahler"],
        "regenerated": [
            "cuenca",
            "red_drenaje_recortada",
            "morfometria",
            "cauce_principal",
            "subcuencas",
            "figuras",
            "informe_pdf",
            "plano_pdf",
        ],
    }
