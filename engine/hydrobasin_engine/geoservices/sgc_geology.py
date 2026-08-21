from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import geopandas as gpd
import shapely
from shapely.geometry import shape

from ..spatial_utils import CRS_WGS84, ensure_valid_geometries

SGC_GEOLOGY_2023_MAPSERVER = (
    "https://geoportal.sgc.gov.co/arcgis/rest/services/Mapa_Geologico_Colombia/Mapa_Geologico_Colombia_V2023/MapServer/733"
)


def fetch_sgc_geology(
    watershed_gdf: gpd.GeoDataFrame,
    service_url: str = SGC_GEOLOGY_2023_MAPSERVER,
    timeout_sec: int = 40,
    page_size: int = 1000,
) -> gpd.GeoDataFrame:
    """Consulta el servicio oficial del Servicio Geológico Colombiano (SGC) para Geología/Litología
    (Mapa Geológico de Colombia V2023 - Unidades Cronoestratigráficas) únicamente para el área de la cuenca,
    manejando paginación y recorte exacto.
    """
    if watershed_gdf.empty:
        raise ValueError("El GeoDataFrame de la cuenca está vacío.")

    ws_4326 = watershed_gdf.to_crs(CRS_WGS84) if watershed_gdf.crs != CRS_WGS84 else watershed_gdf
    bounds = ws_4326.total_bounds
    minx, miny, maxx, maxy = bounds

    buf = 0.005
    bbox_str = f"{minx - buf},{miny - buf},{maxx + buf},{maxy + buf}"

    all_features: list[dict[str, Any]] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "geometry": bbox_str,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outSR": "4326",
            "outFields": "OBJECTID,SimboloUC,Descripcion,Edad,CodigoUC",
            "f": "geojson",
            "returnGeometry": "true",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }

        query_url = f"{service_url}/query?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            query_url,
            headers={
                "User-Agent": "HydroBasin-Engine/2.0 (Hydrologic Modeling System; SGC Official Client)",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ConnectionError(
                f"Error al conectar con el servicio oficial del SGC (Mapa Geológico de Colombia): {exc}"
            ) from exc

        if "error" in data:
            err_msg = data["error"].get("message") or str(data["error"])
            raise RuntimeError(f"El servicio del SGC devolvió un error: {err_msg}")

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)

        if len(features) < page_size:
            break

        offset += len(features)

    if not all_features:
        raise ValueError(
            "El servicio oficial del SGC no retornó unidades geológicas para las coordenadas de la cuenca."
        )

    geoms = []
    props_list = []
    for feat in all_features:
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        try:
            s_geom = shape(geom_dict)
            if s_geom and not s_geom.is_empty:
                geoms.append(s_geom)
                props_list.append(feat.get("properties", {}))
        except Exception:
            continue

    if not geoms:
        raise ValueError("No se pudieron reconstruir geometrías válidas desde el servicio del SGC.")

    gdf_raw = gpd.GeoDataFrame(props_list, geometry=geoms, crs=CRS_WGS84)
    gdf_raw = ensure_valid_geometries(gdf_raw)

    # Renombrar columnas para estandarizar
    rename_map = {
        "SimboloUC": "simbolo_uc",
        "Descripcion": "descripcion_geologica",
        "Edad": "edad_geologica",
        "CodigoUC": "codigo_uc",
    }
    gdf_raw = gdf_raw.rename(columns={k: v for k, v in rename_map.items() if k in gdf_raw.columns})

    # Recorte exacto contra la cuenca hidrográfica
    ws_union = ws_4326.geometry.union_all() if hasattr(ws_4326.geometry, "union_all") else ws_4326.geometry.unary_union
    ws_poly_gdf = gpd.GeoDataFrame(geometry=[ws_union], crs=CRS_WGS84)

    gdf_clipped = gpd.clip(gdf_raw, ws_poly_gdf)
    gdf_clipped = ensure_valid_geometries(gdf_clipped)

    if gdf_clipped.empty:
        raise ValueError("El recorte de geología SGC contra el polígono de la cuenca resultó vacío.")

    return gdf_clipped
