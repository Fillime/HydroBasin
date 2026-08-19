from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np

from .dem import cargar_dem, corregir_dem, metadatos_dem, umbral_celdas_desde_area
from .delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto
from .hydrology import acumulacion_flujo, direccion_flujo, orden_strahler
from .io import guardar_raster, guardar_shapefile_zip, guardar_vector, mascara_a_poligono
from .morphometry import parametros_morfometricos
from .report import generar_figuras, generar_informes
from .streams import extraer_red_vectorial
from .subbasins import delimitar_subcuencas

ProgressCallback = Callable[[str, str, int], None]


def _geojson_web(gdf) -> dict:
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
    drainage_threshold: float | None = None,
    minimum_area_km2: float | None = None,
    snap_threshold: float | None = None,
    dem_source: str | None = None,
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
    report("ok", f"DEM válido · {metadata['width']} × {metadata['height']} celdas · {metadata['crs']}", 6)

    if minimum_area_km2 is not None:
        drainage_threshold, metric_resolution = umbral_celdas_desde_area(dem_path, minimum_area_km2)
        report(
            "ok",
            f"Umbral automático · {minimum_area_km2:g} km² ≈ {drainage_threshold:,} celdas · píxel ≈ {metric_resolution[0]:.1f} × {metric_resolution[1]:.1f} m.",
            9,
        )
    else:
        drainage_threshold = float(drainage_threshold or 1000)
        metric_resolution = None

    report("info", "Cargando el DEM en el motor hidrológico…", 11)
    grid, dem = cargar_dem(dem_path)
    report("ok", "DEM cargado correctamente.", 14)

    report("info", "Corrigiendo pits, depresiones y zonas planas del DEM…", 17)
    corrected_dem = corregir_dem(grid, dem)
    report("ok", "Corrección hidrológica del DEM completada.", 27)

    report("info", "Calculando la dirección de flujo mediante el método D8…", 30)
    flow_direction = direccion_flujo(grid, corrected_dem)
    report("ok", "Dirección de flujo calculada.", 36)

    report("info", "Calculando la acumulación de flujo en cada celda…", 39)
    accumulation = acumulacion_flujo(grid, flow_direction)
    report("ok", "Acumulación de flujo calculada.", 47)

    x_dem, y_dem = transformar_punto(x, y, point_crs, metadata["crs"])
    minimum_accumulation = snap_threshold or drainage_threshold
    report("info", "Ajustando el exutorio a una celda de alta acumulación cercana…", 50)
    x_snap, y_snap = ajustar_punto_salida(grid, accumulation, x_dem, y_dem, minimum_accumulation)
    report("ok", "Exutorio ajustado a la red de flujo.", 54)

    report("info", "Delimitando la cuenca aportante al exutorio…", 57)
    watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)
    report("ok", "Cuenca hidrográfica principal delimitada.", 63)

    report("info", "Vectorizando el límite de la cuenca…", 65)
    watershed = mascara_a_poligono(watershed_mask, dem_path)
    guardar_vector(watershed, output_dir / "cuenca.gpkg")
    guardar_shapefile_zip(watershed, output_dir / "cuenca_shp.zip", "cuenca")
    report("ok", "Polígono de cuenca generado en GeoPackage y Shapefile ZIP.", 68)

    report("info", f"Extrayendo red de drenaje · umbral {drainage_threshold:,.0f} celdas…", 70)
    drainage = extraer_red_vectorial(grid, flow_direction, accumulation, drainage_threshold, crs=metadata["crs"])
    if not drainage.empty:
        guardar_vector(drainage, output_dir / "red_drenaje.gpkg")
        guardar_shapefile_zip(drainage, output_dir / "red_drenaje_shp.zip", "red_drenaje")
        report("ok", f"Red de drenaje generada · {len(drainage)} segmentos · GPKG + SHP ZIP.", 74)
    else:
        report("warning", "No se generaron segmentos con el umbral actual.", 74)

    report("info", "Calculando el orden de corrientes de Strahler…", 76)
    strahler = orden_strahler(grid, flow_direction, accumulation, drainage_threshold)
    strahler_max = int(np.asarray(strahler).max()) if np.asarray(strahler).size else 0
    report("ok", f"Orden de Strahler calculado · orden máximo {strahler_max}.", 80)

    report("info", "Delimitando subcuencas internas a partir de confluencias D8…", 82)
    subbasin_labels, subbasins = delimitar_subcuencas(
        flow_direction,
        accumulation,
        watershed_mask,
        metadata["transform"],
        metadata["crs"],
        drainage_threshold,
    )
    subbasin_count = int(len(subbasins))
    if subbasin_count:
        guardar_vector(subbasins, output_dir / "subcuencas.gpkg")
        guardar_shapefile_zip(subbasins, output_dir / "subcuencas_shp.zip", "subcuencas")
        report("ok", f"Subcuencas generadas · {subbasin_count} unidades · GPKG + SHP ZIP.", 86)
    else:
        report("warning", "No se pudieron generar subcuencas con el umbral actual.", 86)

    report("info", "Guardando rásteres técnicos…", 88)
    guardar_raster(output_dir / "dem_corregido.tif", corrected_dem, dem_path)
    guardar_raster(output_dir / "direccion_flujo.tif", flow_direction, dem_path)
    guardar_raster(output_dir / "acumulacion_flujo.tif", accumulation, dem_path)
    guardar_raster(output_dir / "cuenca_mask.tif", watershed_mask.astype("uint8"), dem_path, nodata=0)
    guardar_raster(output_dir / "strahler.tif", strahler, dem_path, nodata=0)
    guardar_raster(output_dir / "subcuencas.tif", subbasin_labels.astype("int32"), dem_path, nodata=0)

    report("info", "Calculando parámetros morfométricos…", 90)
    metrics = parametros_morfometricos(watershed)
    summary = {
        "dem_source": dem_source or "GeoTIFF cargado por el usuario",
        "crs_dem": metadata["crs"],
        "dem_width": metadata["width"],
        "dem_height": metadata["height"],
        "dem_resolution": [float(metadata["resolution"][0]), float(metadata["resolution"][1])],
        "metric_resolution_m": list(metric_resolution) if metric_resolution else None,
        "outlet_original": {"x": x, "y": y, "crs": point_crs},
        "outlet_snapped": {"x": x_snap, "y": y_snap, "crs": metadata["crs"]},
        "drainage_threshold": float(drainage_threshold),
        "minimum_area_km2": minimum_area_km2,
        "strahler_max": strahler_max,
        "subbasin_count": subbasin_count,
        **metrics,
    }

    report("info", "Generando cartografía técnica enfocada a la cuenca…", 92)
    figures = generar_figuras(
        output_dir,
        grid,
        dem,
        corrected_dem,
        accumulation,
        watershed_mask,
        strahler,
        watershed,
        drainage,
        subbasins=subbasins,
    )
    report("ok", "Cartografía de DEM, relieve, acumulación, drenaje, Strahler y subcuencas generada.", 96)

    report("info", "Generando fuente LaTeX y compilando el PDF con Tectonic…", 97)
    report_files = generar_informes(output_dir, summary, figures, subbasins=subbasins)
    if report_files.get("compiled"):
        report("ok", "Informe PDF compilado correctamente desde LaTeX con Tectonic.", 99)
    elif report_files.get("compiler_found"):
        detail = report_files.get("compile_error") or "Error de compilación no especificado."
        report("warning", f"La fuente .tex fue generada, pero Tectonic no pudo compilar el PDF: {detail}", 99)
    else:
        report("warning", "La fuente .tex fue generada, pero Tectonic no está disponible en el entorno del backend. Reinstala requirements.txt.", 99)

    result = {
        "summary": summary,
        "watershed_geojson": _geojson_web(watershed),
        "drainage_geojson": _geojson_web(drainage),
        "subbasins_geojson": _geojson_web(subbasins),
        "figures": figures,
        "report": report_files,
    }
    (output_dir / "resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report("ok", "Análisis completado. Cuenca, subcuencas, diagramas e informe listos.", 100)
    return result
