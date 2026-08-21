from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import geopandas as gpd
import shapely
from shapely.geometry import shape

from ..spatial_utils import CRS_WGS84, ensure_valid_geometries

IDEAM_CORINE_2018_FEATURESERVER = (
    "https://visualizador.ideam.gov.co/gisserver/rest/services/Estado_Cobertura_Tierra/FeatureServer/3"
)


def fetch_ideam_corine_2018(
    watershed_gdf: gpd.GeoDataFrame,
    service_url: str = IDEAM_CORINE_2018_FEATURESERVER,
    timeout_sec: int = 40,
    page_size: int = 1000,
) -> gpd.GeoDataFrame:
    """Consulta el FeatureServer oficial del IDEAM para Coberturas de la Tierra 2018 (CORINE Land Cover)
    únicamente para el área de la cuenca, manejando paginación y recorte exacto.
    """
    if watershed_gdf.empty:
        raise ValueError("El GeoDataFrame de la cuenca está vacío.")

    # Asegurar WGS84 para la consulta espacial BBOX
    ws_4326 = watershed_gdf.to_crs(CRS_WGS84) if watershed_gdf.crs != CRS_WGS84 else watershed_gdf
    bounds = ws_4326.total_bounds  # [minx, miny, maxx, maxy]
    minx, miny, maxx, maxy = bounds

    # Pequeño buffer de seguridad en el bbox para capturar bordes
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
            "outFields": "objectid,codigo,leyenda,nivel_1,nivel_2,nivel_3,nivel_4",
            "f": "geojson",
            "returnGeometry": "true",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }

        query_url = f"{service_url}/query?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            query_url,
            headers={
                "User-Agent": "HydroBasin-Engine/2.0 (Hydrologic Modeling System; IDEAM Official Client)",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ConnectionError(
                f"Error al conectar con el FeatureServer oficial del IDEAM (CORINE 2018): {exc}"
            ) from exc

        if "error" in data:
            err_msg = data["error"].get("message") or str(data["error"])
            raise RuntimeError(f"El servicio del IDEAM devolvió un error: {err_msg}")

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)

        # Si devolvió menos registros que el tamaño de página, se completó la consulta
        if len(features) < page_size:
            break

        offset += len(features)

    if not all_features:
        raise ValueError(
            "El servicio oficial del IDEAM no retornó coberturas CORINE 2018 para las coordenadas de la cuenca."
        )

    # Construir GeoDataFrame a partir de las geometrías GeoJSON
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
        raise ValueError("No se pudieron reconstruir geometrías válidas desde el servicio del IDEAM.")

    gdf_raw = gpd.GeoDataFrame(props_list, geometry=geoms, crs=CRS_WGS84)
    gdf_raw = ensure_valid_geometries(gdf_raw)

    # Normalizar campos de código y descripción
    def _parse_code(row):
        val = row.get("codigo") or row.get("leyenda") or row.get("nivel_3") or row.get("nivel_2")
        if val is None:
            return None
        # Limpiar strings no numéricos si los hubiera
        clean = "".join(ch for ch in str(val) if ch.isdigit())
        return int(clean) if clean else None

    gdf_raw["codigo_corine"] = gdf_raw.apply(_parse_code, axis=1)

    # Recorte exacto contra la cuenca hidrográfica
    ws_union = ws_4326.geometry.union_all() if hasattr(ws_4326.geometry, "union_all") else ws_4326.geometry.unary_union
    ws_poly_gdf = gpd.GeoDataFrame(geometry=[ws_union], crs=CRS_WGS84)

    gdf_clipped = gpd.clip(gdf_raw, ws_poly_gdf)
    gdf_clipped = ensure_valid_geometries(gdf_clipped)

    if gdf_clipped.empty:
        raise ValueError("El recorte de coberturas CORINE contra el polígono de la cuenca resultó vacío.")

    return gdf_clipped
