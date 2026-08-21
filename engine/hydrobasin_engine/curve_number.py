from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from .geoservices.ideam_corine import fetch_ideam_corine_2018
from .geoservices.sgc_geology import fetch_sgc_geology
from .hydrologic_soils import reclassify_geology_hsg
from .landcover import reclassify_landcover_scs
from .spatial_utils import (
    CRS_NATIONAL,
    CRS_WGS84,
    compute_areas_km2,
    ensure_valid_geometries,
    save_to_geojson_simplified,
    save_to_gpkg,
    to_magna_sirgas_9377,
)

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_CN_LOOKUP_CSV = DATA_DIR / "cn2_lookup.csv"


def load_cn2_lookup(csv_path: Path | None = None) -> pd.DataFrame:
    """Carga la matriz metodológica de búsqueda de CN II (USDA-NRCS)."""
    path = csv_path or DEFAULT_CN_LOOKUP_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró la matriz metodológica de CN II: {path}. "
            "HydroBasin no utiliza valores CN hardcodeados en el código fuente."
        )

    df = pd.read_csv(path)
    # Normalizar columnas
    df["uso_scs"] = df["uso_scs"].astype(str).str.strip()
    df["condicion_hidrologica"] = df["condicion_hidrologica"].astype(str).str.strip()
    df["grupo_hidrologico"] = df["grupo_hidrologico"].astype(str).str.strip().str.upper()
    df["cn_ii"] = df["cn_ii"].astype(float)
    return df


def _plot_thematic_map(
    gdf: gpd.GeoDataFrame,
    column: str,
    title: str,
    output_path: Path,
    cmap: str = "tab20",
    legend_title: str = "",
    watershed_gdf: gpd.GeoDataFrame | None = None,
) -> str | None:
    """Genera un mapa temático vectorial elegante y de alta resolución."""
    if gdf.empty:
        return None

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(8.0, 6.0), dpi=200)

        # Fondo divisoria
        if watershed_gdf is not None and not watershed_gdf.empty:
            ws_wgs = watershed_gdf.to_crs(CRS_WGS84)
            ws_wgs.boundary.plot(ax=ax, color="#0F172A", linewidth=1.5, linestyle="--", label="Divisoria de Cuenca", zorder=4)

        gdf_wgs = gdf.to_crs(CRS_WGS84)
        is_numeric = np.issubdtype(gdf_wgs[column].dtype, np.number)

        if is_numeric:
            gdf_wgs.plot(
                column=column,
                ax=ax,
                cmap=cmap,
                legend=True,
                legend_kwds={"label": legend_title, "shrink": 0.75, "pad": 0.02},
                edgecolor="#475569",
                linewidth=0.3,
                zorder=2,
            )
        else:
            gdf_wgs.plot(
                column=column,
                ax=ax,
                cmap=cmap,
                legend=True,
                legend_kwds={"title": legend_title, "bbox_to_anchor": (1.02, 1), "loc": "upper left", "fontsize": 8},
                edgecolor="#475569",
                linewidth=0.3,
                zorder=2,
            )

        ax.set_title(title, fontsize=10.5, fontweight="bold", pad=10, color="#176B73")
        ax.set_xlabel("Longitud (WGS84)", fontsize=8)
        ax.set_ylabel("Latitud (WGS84)", fontsize=8)
        ax.grid(True, linestyle=":", alpha=0.5, color="#94A3B8")
        ax.tick_params(labelsize=7.5)

        fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return str(output_path)
    except Exception:
        return None


def compute_spatial_curve_number(
    watershed_gdf: gpd.GeoDataFrame,
    output_dir: Path,
    figures_dir: Path | None = None,
    tolerance_unclassified_pct: float = 0.1,  # 0.1% de tolerancia geométrica
) -> tuple[dict[str, Any], dict[str, str]]:
    """Calcula automáticamente el Número de Curva SCS (CN II) a partir de los FeatureServers oficiales
    del IDEAM (CORINE 2018) y del SGC (Geología/Litología 2023), realizando la intersección espacial
    en MAGNA-SIRGAS Origen-Nacional (EPSG:9377).
    """
    output_dir = Path(output_dir)
    fig_dir = figures_dir or (output_dir / "figuras")
    gis_dir = output_dir / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    gpkg_path = gis_dir / "cn_analysis.gpkg"

    # 1. Calcular área real de la cuenca en EPSG:9377
    ws_projected = to_magna_sirgas_9377(watershed_gdf)
    total_ws_area_km2 = float((ws_projected.geometry.area.sum()) / 1_000_000.0)

    if total_ws_area_km2 <= 0:
        raise ValueError("El área de la cuenca delimitada es menor o igual a cero.")

    # 2. Descargar y reclasificar Coberturas CORINE 2018 (IDEAM)
    gdf_corine_raw = fetch_ideam_corine_2018(watershed_gdf)
    gdf_corine = reclassify_landcover_scs(gdf_corine_raw)

    # 3. Descargar y reclasificar Geología/Litología (SGC)
    gdf_geology_raw = fetch_sgc_geology(watershed_gdf)
    gdf_geology = reclassify_geology_hsg(gdf_geology_raw)

    # 4. Intersección espacial de Cobertura y Geología
    # Asegurar WGS84 para el overlay topológico
    gdf_corine_wgs = gdf_corine.to_crs(CRS_WGS84)
    gdf_geology_wgs = gdf_geology.to_crs(CRS_WGS84)

    # Conservar columnas esenciales para la intersección
    cols_corine = ["codigo_corine", "uso_scs", "condicion_hidrologica", "cobertura_nombre", "geometry"]
    cols_geol = ["simbolo_uc", "descripcion_geologica", "grupo_hidrologico", "criterio_hsg", "geometry"]

    c_clean = ensure_valid_geometries(gdf_corine_wgs[[c for c in cols_corine if c in gdf_corine_wgs.columns]])
    g_clean = ensure_valid_geometries(gdf_geology_wgs[[c for c in cols_geol if c in gdf_geology_wgs.columns]])

    try:
        overlay_gdf = gpd.overlay(c_clean, g_clean, how="intersection")
    except Exception as exc:
        raise RuntimeError(f"Error en la intersección espacial de Cobertura y Geología: {exc}") from exc

    overlay_gdf = ensure_valid_geometries(overlay_gdf)
    if overlay_gdf.empty:
        raise ValueError("La intersección espacial entre coberturas CORINE y geología SGC resultó vacía.")

    # 5. Cargar tabla canónica CN II y asignar valores a cada unidad homogénea
    cn_lut = load_cn2_lookup()
    cn_map = {}
    for _, r in cn_lut.iterrows():
        key = (r["uso_scs"].strip(), r["condicion_hidrologica"].strip(), r["grupo_hidrologico"].strip().upper())
        cn_map[key] = float(r["cn_ii"])

    cn_values = []
    is_classified_list = []

    for _, row in overlay_gdf.iterrows():
        uso = str(row.get("uso_scs") or "").strip()
        cond = str(row.get("condicion_hidrologica") or "").strip()
        hsg = str(row.get("grupo_hidrologico") or "").strip().upper()

        key = (uso, cond, hsg)
        if key in cn_map:
            cn_val = cn_map[key]
            cn_values.append(cn_val)
            is_classified_list.append(True)
        else:
            cn_values.append(None)
            is_classified_list.append(False)

    overlay_gdf["cn_ii"] = cn_values
    overlay_gdf["is_classified"] = is_classified_list

    # 6. Cálculo unificado de áreas reales en EPSG:9377
    overlay_gdf["area_km2"] = compute_areas_km2(overlay_gdf)
    overlay_gdf["cn_x_area"] = overlay_gdf.apply(
        lambda r: round(r["cn_ii"] * r["area_km2"], 6) if pd.notnull(r["cn_ii"]) else 0.0, axis=1
    )

    # 7. Balance y validación de cobertura sobre la cuenca
    total_overlay_area_km2 = float(overlay_gdf["area_km2"].sum())
    classified_gdf = overlay_gdf[overlay_gdf["is_classified"] == True]
    unclassified_gdf = overlay_gdf[overlay_gdf["is_classified"] == False]

    classified_area_km2 = float(classified_gdf["area_km2"].sum())
    unclassified_area_km2 = float(unclassified_gdf["area_km2"].sum())

    unclassified_pct = (unclassified_area_km2 / total_ws_area_km2 * 100.0) if total_ws_area_km2 > 0 else 100.0
    classified_pct = (classified_area_km2 / total_ws_area_km2 * 100.0) if total_ws_area_km2 > 0 else 0.0

    # 8. Determinación de estado y CN ponderado
    # El objetivo es clasificar el 100% de la cuenca con tolerancia pequeña para slivers geométricos
    is_complete = unclassified_pct <= tolerance_unclassified_pct and classified_area_km2 > 0

    if is_complete:
        status = "ok"
        cn_weighted = float(classified_gdf["cn_x_area"].sum() / classified_area_km2)
        s_retention_mm = (25400.0 / cn_weighted) - 254.0
        ia_mm = 0.2 * s_retention_mm
    else:
        status = "incomplete"
        cn_weighted = None
        s_retention_mm = None
        ia_mm = None

    # 9. Agregar unidades homogéneas para reporte y Excel
    # Agrupar por (cobertura_nombre, uso_scs, condicion_hidrologica, simbolo_uc, descripcion_geologica, grupo_hidrologico, cn_ii)
    group_cols = ["cobertura_nombre", "uso_scs", "condicion_hidrologica", "simbolo_uc", "descripcion_geologica", "grupo_hidrologico", "cn_ii"]
    agg_units = []

    grouped = overlay_gdf.groupby(group_cols, dropna=False)
    for keys, grp in grouped:
        u_area = float(grp["area_km2"].sum())
        u_pct = (u_area / total_ws_area_km2 * 100.0) if total_ws_area_km2 > 0 else 0.0
        u_cn = keys[6]
        agg_units.append({
            "cobertura": keys[0] or "N/D",
            "uso_scs": keys[1] or "No clasificado",
            "condicion": keys[2] or "N/D",
            "simbolo_uc": keys[3] or "N/D",
            "litologia": keys[4] or "N/D",
            "grupo_suelo": keys[5] or "No clasificado",
            "cn": round(u_cn, 2) if pd.notnull(u_cn) else None,
            "area_km2": round(u_area, 4),
            "porcentaje_cuenca": round(u_pct, 2),
            "nc_ai": round(u_cn * u_area, 4) if pd.notnull(u_cn) else 0.0,
            "is_classified": pd.notnull(u_cn),
        })

    # Ordenar unidades por área descendente
    agg_units.sort(key=lambda x: x["area_km2"], reverse=True)

    # 10. Guardar en GeoPackage multi-capa y GeoJSONs simplificados
    layers_gpkg = {
        "coberturas_corine": gdf_corine,
        "grupos_hidrologicos": gdf_geology,
        "unidades_homogeneas_cn": overlay_gdf,
    }
    try:
        save_to_gpkg(layers_gpkg, gpkg_path)
    except Exception:
        pass

    try:
        save_to_geojson_simplified(gdf_corine, output_dir / "coberturas_corine.geojson")
        save_to_geojson_simplified(gdf_geology, output_dir / "grupos_hidrologicos.geojson")
        save_to_geojson_simplified(overlay_gdf, output_dir / "unidades_homogeneas_cn.geojson")
    except Exception:
        pass

    # 11. Generación de Mapas Cartográficos Temáticos
    figs_dict: dict[str, str] = {}
    fig_corine = _plot_thematic_map(
        gdf_corine,
        column="uso_scs",
        title="Coberturas de la Tierra CORINE Land Cover 2018 (IDEAM)",
        output_path=fig_dir / "08_coberturas_corine.png",
        cmap="tab20",
        legend_title="Uso / Cobertura SCS",
        watershed_gdf=watershed_gdf,
    )
    if fig_corine:
        figs_dict["corine_landcover"] = "figuras/08_coberturas_corine.png"

    fig_hsg = _plot_thematic_map(
        gdf_geology,
        column="grupo_hidrologico",
        title="Grupos Hidrológicos de Suelo HSG (Geología SGC 2023)",
        output_path=fig_dir / "09_grupos_hidrologicos.png",
        cmap="Set2",
        legend_title="Grupo HSG (A/B/C/D)",
        watershed_gdf=watershed_gdf,
    )
    if fig_hsg:
        figs_dict["hydrologic_soils"] = "figuras/09_grupos_hidrologicos.png"

    fig_cn = _plot_thematic_map(
        overlay_gdf[overlay_gdf["cn_ii"].notnull()],
        column="cn_ii",
        title=f"Distribución Espacial del Número de Curva SCS (CN II ponderado = {cn_weighted:.2f})" if cn_weighted else "Distribución Espacial del Número de Curva SCS (CN II)",
        output_path=fig_dir / "10_distribucion_cn.png",
        cmap="YlGnBu",
        legend_title="Valor CN II",
        watershed_gdf=watershed_gdf,
    )
    if fig_cn:
        figs_dict["curve_number"] = "figuras/10_distribucion_cn.png"

    summary_result = {
        "status": status,
        "fuente_corine": "IDEAM (FeatureServer Oficial 2018)",
        "fuente_geologia": "SGC (Mapa Geológico de Colombia V2023 - Unidades Cronoestratigráficas)",
        "cn_weighted": round(cn_weighted, 3) if cn_weighted is not None else None,
        "s_retention_mm": round(s_retention_mm, 3) if s_retention_mm is not None else None,
        "ia_abstraction_mm": round(ia_mm, 3) if ia_mm is not None else None,
        "total_area_km2": round(total_ws_area_km2, 4),
        "classified_area_km2": round(classified_area_km2, 4),
        "unclassified_area_km2": round(unclassified_area_km2, 4),
        "classified_percentage": round(classified_pct, 2),
        "unclassified_percentage": round(unclassified_pct, 2),
        "homogeneous_units_count": len(agg_units),
        "tolerance_applied_pct": tolerance_unclassified_pct,
        "gpkg_path": str(gpkg_path),
        "units": agg_units,
        "table_versions": {
            "corine_to_scs": "1.0 (IDEAM 2018 CLC Colombia)",
            "lithology_to_hsg": "1.0 (SGC 2023 Litologia/UCG)",
            "cn2_lookup": "1.0 (USDA-NRCS TR-55 / NEH-4 AMC II)",
        },
    }

    return summary_result, figs_dict


def compute_curve_number(
    total_area_km2: float,
    units: list[dict[str, Any]] | None = None,
    cn_weighted: float | None = None,
    output_fig_path: Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Función de compatibilidad para cálculo de CN con unidades documentadas precalculadas."""
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
