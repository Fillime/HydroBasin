from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import geopandas as gpd
import numpy as np
import rasterio
from pysheds.grid import Grid
from rasterio.enums import Resampling

from .curve_number import compute_curve_number
from .delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto
from .dem import metadatos_dem, umbral_celdas_desde_area
from .hydrologic_modeling import compute_peak_discharges
from .idf_curves import compute_idf_curves
from .io import guardar_raster, guardar_shapefile_zip, guardar_vector, mascara_a_poligono
from .location import resolve_administrative_location
from .main_channel import extraer_cauce_principal, tiempos_concentracion
from .meteorology import fetch_ideam_stations, plot_stations_map
from .morphometry import parametros_morfometricos
from .report import generar_figuras
from .report_professional import generar_informes
from .streams import extraer_red_vectorial
from .subbasins import delimitar_subcuencas
from .thiessen import compute_thiessen_polygons

ProgressCallback = Callable[[str, str, int], None]


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


def _dem_context_preview(path: str | Path, max_dim: int = 1400):
    with rasterio.open(path) as src:
        scale = min(1.0, max_dim / max(src.width, src.height))
        width = max(1, int(src.width * scale))
        height = max(1, int(src.height * scale))
        return src.read(1, out_shape=(height, width), resampling=Resampling.bilinear)


def reprocess_stage(
    results_dir: Path,
    mode: str,  # 'report' | 'hydrology' | 'streams' | 'delineation'
    x: float,
    y: float,
    point_crs: str = "EPSG:4326",
    minimum_area_km2: float = 5.0,
    project_name: str | None = None,
    client: str | None = None,
    calculated_by: str | None = None,
    reviewed_by: str | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    """Re-procesa el análisis a partir de una etapa específica reutilizando cálculos previos."""
    results_dir = Path(results_dir).resolve()

    def report(level: str, message: str, percent: int) -> None:
        if progress:
            progress(level, message, percent)

    # 1. Cargar summary existente (resumen.json o summary.json)
    summary_path = results_dir / "resumen.json"
    if not summary_path.exists():
        summary_path = results_dir / "summary.json"
    if not summary_path.exists():
        json_candidates = [p for p in results_dir.glob("*.json") if "preview" not in p.name]
        if json_candidates:
            summary_path = json_candidates[0]
        else:
            raise FileNotFoundError("No se encontró el archivo resumen.json del análisis previo.")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    def save_summary():
        text = json.dumps(summary, indent=2, ensure_ascii=False)
        (results_dir / "resumen.json").write_text(text, encoding="utf-8")
        (results_dir / "summary.json").write_text(text, encoding="utf-8")

    # Actualizar metadatos si fueron provistos
    if project_name:
        summary["project_name"] = project_name
    if client:
        summary["client"] = client
    if calculated_by:
        summary["calculated_by"] = calculated_by
    if reviewed_by:
        summary["reviewed_by"] = reviewed_by

    # Cargar vectores existentes
    watershed_path = results_dir / "cuenca.gpkg"
    drainage_path = results_dir / "red_drenaje.gpkg"
    subbasins_path = results_dir / "subcuencas.gpkg"
    channel_path = results_dir / "cauce_principal.gpkg"

    watershed = gpd.read_file(watershed_path) if watershed_path.exists() else None
    drainage = gpd.read_file(drainage_path) if drainage_path.exists() else None
    subbasins = gpd.read_file(subbasins_path) if subbasins_path.exists() else None
    main_channel = gpd.read_file(channel_path) if channel_path.exists() else None

    # Recoger figuras existentes
    figures = {}
    for p in results_dir.glob("figuras/*.png"):
        rel = f"figuras/{p.name}"
        if "00_ubicacion" in p.name:
            figures["location_satellite"] = rel
        elif "01_dem" in p.name:
            figures["dem"] = rel
        elif "03_acumulacion" in p.name:
            figures["accumulation"] = rel
        elif "04_cuenca" in p.name:
            figures["watershed"] = rel
        elif "05_strahler" in p.name:
            figures["strahler"] = rel
        elif "06_subcuencas" in p.name:
            figures["subbasins"] = rel
        elif "07_perfil" in p.name:
            figures["profile"] = rel
        elif "08_estaciones" in p.name:
            figures["stations_map"] = rel
        elif "09_poligonos" in p.name:
            figures["thiessen_map"] = rel
        elif "10_curvas" in p.name:
            figures["idf_curves"] = rel
        elif "11_distribucion" in p.name:
            figures["curve_number"] = rel
        elif "12_hidrogramas" in p.name:
            figures["hydrographs"] = rel
        elif "plano" in p.name:
            figures["plan"] = rel

    # =========================================================================
    # MODO 1: RE-GENERAR SOLO INFORME Y PLANOS
    # =========================================================================
    if mode == "report":
        report("info", "Recompilando informe técnico y planos con los nuevos metadatos…", 20)
        report_files = generar_informes(
            results_dir,
            summary,
            figures,
            subbasins=subbasins,
            main_channel=main_channel,
            watershed=watershed,
            drainage=drainage,
        )
        save_summary()
        report("ok", "Informe técnico y planos recompilados exitosamente.", 100)
        return {
            "summary": summary,
            "watershed_geojson": _geojson_web(watershed),
            "drainage_geojson": _geojson_web(drainage),
            "subbasins_geojson": _geojson_web(subbasins),
            "report": report_files,
            "figures": figures,
        }

    # =========================================================================
    # MODO 2: RE-CALCULAR HIDROLOGÍA Y CAUDALES (IDEAM, THIESSEN, IDF, CN, Qp)
    # =========================================================================
    if mode == "hydrology":
        report("info", "Actualizando consulta de estaciones meteorológicas del IDEAM…", 20)
        out_x = summary.get("outlet_original", {}).get("x", x)
        out_y = summary.get("outlet_original", {}).get("y", y)
        loc = resolve_administrative_location(float(out_y), float(out_x))
        stations = fetch_ideam_stations(float(out_y), float(out_x), department=loc.get("department", ""), radius_km=50.0)
        summary["ideam_stations"] = stations

        fig_dir = results_dir / "figuras"
        fig_dir.mkdir(parents=True, exist_ok=True)

        st_fig_path = fig_dir / "08_estaciones_ideam.png"
        st_fig = plot_stations_map(st_fig_path, stations, watershed, float(out_y), float(out_x), loc)
        if st_fig:
            figures["stations_map"] = "figuras/08_estaciones_ideam.png"

        report("info", "Recalculando Polígonos de Thiessen…", 40)
        thiessen_fig_path = fig_dir / "09_poligonos_thiessen.png"
        thiessen_weights, thiessen_fig = compute_thiessen_polygons(stations, watershed, thiessen_fig_path)
        summary["thiessen_weights"] = thiessen_weights
        if thiessen_fig:
            figures["thiessen_map"] = "figuras/09_poligonos_thiessen.png"

        report("info", "Recalculando Curvas IDF y lluvias de diseño…", 60)
        tc_avg_h = float(summary.get("tc_promedio_h") or 1.0)
        tc_avg_min = tc_avg_h * 60.0
        idf_fig_path = fig_dir / "10_curvas_idf.png"
        base_st_name = stations[0]["nombre"] if stations else "Estación Regional"
        idf_data, idf_fig = compute_idf_curves(tc_avg_min, station_name=base_st_name, output_fig_path=idf_fig_path)
        summary["idf_curves"] = idf_data
        if idf_fig:
            figures["idf_curves"] = "figuras/10_curvas_idf.png"

        report("info", "Recalculando Número de Curva SCS (CN)…", 75)
        cn_fig_path = fig_dir / "11_distribucion_cn.png"
        total_area = float(summary.get("area_km2") or 1.0)
        cn_data, cn_fig = compute_curve_number(total_area, output_fig_path=cn_fig_path)
        summary["curve_number"] = cn_data
        summary["cn_weighted"] = cn_data["cn_weighted"]
        if cn_fig:
            figures["curve_number"] = "figuras/11_distribucion_cn.png"

        report("info", "Modelando caudales máximos de diseño por Tr…", 85)
        hydro_fig_path = fig_dir / "12_hidrogramas_diseno.png"
        peak_flows, hydro_fig = compute_peak_discharges(
            total_area,
            tc_avg_h,
            cn_data["cn_weighted"],
            idf_data["design_intensities_mm_h"],
            output_fig_path=hydro_fig_path,
        )
        summary["hydrologic_modeling"] = peak_flows
        summary["peak_discharges"] = peak_flows["results_by_return_period"]
        if hydro_fig:
            figures["hydrographs"] = "figuras/12_hidrogramas_diseno.png"

        report("info", "Recompilando informe técnico y planos A3…", 92)
        report_files = generar_informes(
            results_dir,
            summary,
            figures,
            subbasins=subbasins,
            main_channel=main_channel,
            watershed=watershed,
            drainage=drainage,
        )
        save_summary()
        report("ok", "Módulo hidrológico, informe técnico y planos actualizados.", 100)
        return {
            "summary": summary,
            "watershed_geojson": _geojson_web(watershed),
            "drainage_geojson": _geojson_web(drainage),
            "subbasins_geojson": _geojson_web(subbasins),
            "report": report_files,
            "figures": figures,
        }

    # =========================================================================
    # MODO 3: RE-CALCULAR DESDE DRENAJES / SUBCUENCAS (CAMBIO DE ÁREA MÍNIMA)
    # =========================================================================
    if mode in ("streams", "delineation"):
        dem_path = results_dir / "dem_corregido.tif"
        if not dem_path.exists():
            dem_path = results_dir.parent / "input" / "dem.tif"

        report("info", "Cargando grilla y matrices de flujo D8 desde almacenamiento…", 15)
        grid = Grid.from_raster(str(dem_path))
        corrected_dem = grid.read_raster(str(dem_path))
        flow_direction = grid.flowdir(corrected_dem)
        accumulation = grid.accumulation(flow_direction)

        metadata = metadatos_dem(dem_path)
        d_thresh = umbral_celdas_desde_area(minimum_area_km2, metadata["resolution"], metadata["crs"])
        summary["minimum_area_km2"] = minimum_area_km2
        summary["drainage_threshold"] = float(d_thresh)

        if mode == "delineation":
            report("info", "Ajustando nuevo exutorio a eje de drenaje…", 30)
            x_m, y_m = transformar_punto(x, y, point_crs, metadata["crs"])
            x_snap, y_snap = ajustar_punto_salida(grid, accumulation, x_m, y_m, threshold=d_thresh)
            summary["outlet_original"] = {"x": x, "y": y, "crs": point_crs}
            summary["outlet_snapped"] = {"x": x_snap, "y": y_snap, "crs": metadata["crs"]}

            report("info", "Delimitando divisoria de la nueva cuenca…", 45)
            watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)
            watershed = mascara_a_poligono(watershed_mask, grid.affine, metadata["crs"])
            guardar_vector(watershed, watershed_path)
            guardar_shapefile_zip(watershed, results_dir / "cuenca_shp.zip", "cuenca")

            # Métricas morfométricas y de relieve
            metrics = parametros_morfometricos(watershed)
            elev_stats = _masked_elevation_stats(corrected_dem, watershed_mask)
            summary.update(metrics)
            summary.update(elev_stats)
        else:
            # Reutilizar watershed_mask existente
            mask_raster_path = results_dir / "cuenca_mask.tif"
            if mask_raster_path.exists():
                with rasterio.open(mask_raster_path) as m_src:
                    watershed_mask = m_src.read(1).astype(bool)
            else:
                x_snap = summary.get("outlet_snapped", {}).get("x", x)
                y_snap = summary.get("outlet_snapped", {}).get("y", y)
                watershed_mask = delimitar_cuenca(grid, flow_direction, x_snap, y_snap)

        report("info", f"Extrayendo red de drenaje con umbral de {minimum_area_km2} km²…", 60)
        drainage, strahler = extraer_red_vectorial(
            grid,
            flow_direction,
            accumulation,
            d_thresh,
            metadata["crs"],
            watershed_mask=watershed_mask,
        )
        guardar_vector(drainage, drainage_path)
        guardar_shapefile_zip(drainage, results_dir / "red_drenaje_shp.zip", "red_drenaje")
        summary["strahler_max"] = int(drainage["strahler"].max()) if (drainage is not None and not drainage.empty and "strahler" in drainage.columns) else 1

        report("info", "Delimitando subcuencas hidrológicas…", 70)
        subbasins = delimitar_subcuencas(grid, flow_direction, accumulation, d_thresh, metadata["crs"], watershed_mask=watershed_mask)
        if subbasins is not None and not subbasins.empty:
            guardar_vector(subbasins, subbasins_path)
            guardar_shapefile_zip(subbasins, results_dir / "subcuencas_shp.zip", "subcuencas")
            summary["subbasin_count"] = len(subbasins)
        else:
            summary["subbasin_count"] = 0

        report("info", "Trazando cauce principal y perfil altimétrico…", 78)
        x_s = summary.get("outlet_snapped", {}).get("x", x)
        y_s = summary.get("outlet_snapped", {}).get("y", y)
        main_channel, ch_metrics = extraer_cauce_principal(grid, flow_direction, accumulation, corrected_dem, x_s, y_s, metadata["crs"], watershed_mask=watershed_mask)
        guardar_vector(main_channel, channel_path)
        guardar_shapefile_zip(main_channel, results_dir / "cauce_principal_shp.zip", "cauce_principal")
        tc_metrics = tiempos_concentracion(ch_metrics["main_channel_length_km"], ch_metrics["main_channel_slope_percent"])
        summary.update(ch_metrics)
        summary.update(tc_metrics)

        # Re-ejecutar hidrología completa
        report("info", "Actualizando suite hidrológica (IDEAM, Thiessen, IDF, CN, Caudales)…", 85)
        out_x = summary.get("outlet_original", {}).get("x", x)
        out_y = summary.get("outlet_original", {}).get("y", y)
        loc = resolve_administrative_location(float(out_y), float(out_x))
        stations = fetch_ideam_stations(float(out_y), float(out_x), department=loc.get("department", ""), radius_km=50.0)
        summary["ideam_stations"] = stations

        fig_dir = results_dir / "figuras"
        fig_dir.mkdir(parents=True, exist_ok=True)
        st_fig_path = fig_dir / "08_estaciones_ideam.png"
        plot_stations_map(st_fig_path, stations, watershed, float(out_y), float(out_x), loc)

        thiessen_fig_path = fig_dir / "09_poligonos_thiessen.png"
        th_w, _ = compute_thiessen_polygons(stations, watershed, thiessen_fig_path)
        summary["thiessen_weights"] = th_w

        tc_avg_h = float(summary.get("tc_promedio_h") or 1.0)
        tc_avg_min = tc_avg_h * 60.0
        idf_fig_path = fig_dir / "10_curvas_idf.png"
        base_st_name = stations[0]["nombre"] if stations else "Estación Regional"
        idf_data, _ = compute_idf_curves(tc_avg_min, station_name=base_st_name, output_fig_path=idf_fig_path)
        summary["idf_curves"] = idf_data

        cn_fig_path = fig_dir / "11_distribucion_cn.png"
        total_area = float(summary.get("area_km2") or 1.0)
        cn_data, _ = compute_curve_number(total_area, output_fig_path=cn_fig_path)
        summary["curve_number"] = cn_data
        summary["cn_weighted"] = cn_data["cn_weighted"]

        hydro_fig_path = fig_dir / "12_hidrogramas_diseno.png"
        peak_flows, _ = compute_peak_discharges(
            total_area,
            tc_avg_h,
            cn_data["cn_weighted"],
            idf_data["design_intensities_mm_h"],
            output_fig_path=hydro_fig_path,
        )
        summary["hydrologic_modeling"] = peak_flows
        summary["peak_discharges"] = peak_flows["results_by_return_period"]

        report("info", "Actualizando figuras temáticas y cartografía…", 90)
        dem_context = _dem_context_preview(dem_path)
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
            summary=summary,
            flow_direction=flow_direction,
        )

        figures["stations_map"] = "figuras/08_estaciones_ideam.png"
        figures["thiessen_map"] = "figuras/09_poligonos_thiessen.png"
        figures["idf_curves"] = "figuras/10_curvas_idf.png"
        figures["curve_number"] = "figuras/11_distribucion_cn.png"
        figures["hydrographs"] = "figuras/12_hidrogramas_diseno.png"

        report("info", "Compilando informe técnico y plano A3…", 95)
        report_files = generar_informes(
            results_dir,
            summary,
            figures,
            subbasins=subbasins,
            main_channel=main_channel,
            watershed=watershed,
            drainage=drainage,
        )
        save_summary()
        report("ok", "Re-procesamiento completado exitosamente.", 100)
        return {
            "summary": summary,
            "watershed_geojson": _geojson_web(watershed),
            "drainage_geojson": _geojson_web(drainage),
            "subbasins_geojson": _geojson_web(subbasins),
            "report": report_files,
            "figures": figures,
        }

    raise ValueError(f"Modo de re-procesamiento desconocido: {mode}")
