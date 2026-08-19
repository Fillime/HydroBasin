from __future__ import annotations

import math
import geopandas as gpd


def _utm_crs_aproximado(gdf: gpd.GeoDataFrame):
    if gdf.crs is None:
        raise ValueError("La cuenca no tiene CRS definido.")
    if gdf.crs.is_projected:
        return gdf.crs
    centroid = gdf.to_crs(4326).geometry.unary_union.centroid
    zone = int((centroid.x + 180) // 6) + 1
    epsg = 32600 + zone if centroid.y >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def parametros_morfometricos(cuenca: gpd.GeoDataFrame) -> dict:
    crs_metrico = _utm_crs_aproximado(cuenca)
    g = cuenca.to_crs(crs_metrico)
    geom = g.geometry.unary_union
    area_m2 = geom.area
    perimetro_m = geom.length
    area_km2 = area_m2 / 1e6
    perimetro_km = perimetro_m / 1000
    compacidad = perimetro_m / (2 * math.sqrt(math.pi * area_m2)) if area_m2 else None
    circularidad = 4 * math.pi * area_m2 / (perimetro_m ** 2) if perimetro_m else None
    return {
        "area_km2": area_km2,
        "perimetro_km": perimetro_km,
        "coeficiente_compacidad": compacidad,
        "relacion_circularidad": circularidad,
        "crs_calculo": str(crs_metrico),
    }
