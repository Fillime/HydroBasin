from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import shapely
from shapely.geometry import mapping

CRS_WGS84 = "EPSG:4326"
CRS_NATIONAL = "EPSG:9377"  # MAGNA-SIRGAS / Origen-Nacional


def ensure_valid_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Limpia y repara geometrías inválidas o colapsadas."""
    if gdf.empty:
        return gdf

    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].apply(
        lambda geom: shapely.make_valid(geom) if geom and not geom.is_empty else geom
    )
    # Filtrar geometrías no poligonales resultantes de make_valid
    gdf = gdf[gdf["geometry"].notnull() & ~gdf["geometry"].is_empty]
    gdf = gdf[gdf["geometry"].geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])]

    # Extraer polígonos de GeometryCollections si existieran
    valid_geoms = []
    for geom in gdf["geometry"]:
        if geom.geom_type == "GeometryCollection":
            polys = [g for g in geom.geoms if g.geom_type in ["Polygon", "MultiPolygon"]]
            if polys:
                valid_geoms.append(shapely.unary_union(polys))
            else:
                valid_geoms.append(None)
        else:
            valid_geoms.append(geom)

    gdf["geometry"] = valid_geoms
    gdf = gdf[gdf["geometry"].notnull() & ~gdf["geometry"].is_empty]
    return gdf


def to_magna_sirgas_9377(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reproyecta un GeoDataFrame a MAGNA-SIRGAS Origen-Nacional (EPSG:9377)."""
    if gdf.empty:
        return gdf
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_WGS84)
    if str(gdf.crs).upper() != CRS_NATIONAL.upper():
        gdf = gdf.to_crs(CRS_NATIONAL)
    return ensure_valid_geometries(gdf)


def compute_areas_km2(gdf: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """Calcula el área real en kilómetros cuadrados (km²) proyectada en EPSG:9377."""
    if gdf.empty:
        return gpd.GeoSeries([], dtype=float)

    projected = to_magna_sirgas_9377(gdf)
    # Area en m² convertida a km²
    return (projected.geometry.area / 1_000_000.0).round(6)


def save_to_gpkg(layers: dict[str, gpd.GeoDataFrame], gpkg_path: Path) -> None:
    """Guarda múltiples capas en un GeoPackage SQLite estándar."""
    gpkg_path.parent.mkdir(parents=True, exist_ok=True)
    if gpkg_path.exists():
        try:
            gpkg_path.unlink()
        except Exception:
            pass

    for layer_name, gdf in layers.items():
        if gdf is not None and not gdf.empty:
            gdf_to_write = gdf.copy()
            # Asegurar CRS
            if gdf_to_write.crs is None:
                gdf_to_write = gdf_to_write.set_crs(CRS_WGS84)
            gdf_to_write.to_file(str(gpkg_path), layer=layer_name, driver="GPKG")


def save_to_geojson_simplified(
    gdf: gpd.GeoDataFrame, geojson_path: Path, tolerance_deg: float = 0.00005
) -> None:
    """Exporta una capa GeoJSON simplificada en WGS84 para renderizado óptimo en MapLibre."""
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    if gdf.empty:
        geojson_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
        return

    gdf_wgs84 = gdf.copy()
    if gdf_wgs84.crs is None:
        gdf_wgs84 = gdf_wgs84.set_crs(CRS_WGS84)
    elif str(gdf_wgs84.crs).upper() != CRS_WGS84.upper():
        gdf_wgs84 = gdf_wgs84.to_crs(CRS_WGS84)

    gdf_wgs84 = ensure_valid_geometries(gdf_wgs84)
    if tolerance_deg > 0:
        gdf_wgs84["geometry"] = gdf_wgs84["geometry"].simplify(
            tolerance_deg, preserve_topology=True
        )

    gdf_wgs84.to_file(str(geojson_path), driver="GeoJSON")
