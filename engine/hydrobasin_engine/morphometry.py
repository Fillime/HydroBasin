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


def _rotated_rectangle_axes(geom) -> tuple[float | None, float | None]:
    rect = geom.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    if len(coords) < 4:
        return None, None
    sides = []
    for a, b in zip(coords[:-1], coords[1:]):
        sides.append(math.hypot(b[0] - a[0], b[1] - a[1]))
    if not sides:
        return None, None
    return max(sides), min(sides)


def _classify_form_factor(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.22:
        return "Muy alargada"
    if value < 0.30:
        return "Alargada"
    if value < 0.37:
        return "Ligeramente alargada"
    if value < 0.45:
        return "Ni alargada ni ensanchada"
    if value < 0.60:
        return "Ligeramente ensanchada"
    return "Ensanchada"


def _classify_compactness(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 1.25:
        return "Redonda a oval redonda"
    if value <= 1.50:
        return "Oval redonda a oval oblonga"
    if value <= 1.75:
        return "Oval oblonga a rectangular oblonga"
    return "Rectangular oblonga"


def _classify_elongation(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1.4:
        return "Poco alargada"
    if value < 2.0:
        return "Alargada"
    return "Rectangular"


def _classify_drainage_density(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1.0:
        return "Baja"
    if value < 2.0:
        return "Moderada"
    if value < 3.5:
        return "Alta"
    return "Muy alta"


def parametros_morfometricos(cuenca: gpd.GeoDataFrame, drainage: gpd.GeoDataFrame | None = None) -> dict:
    crs_metrico = _utm_crs_aproximado(cuenca)
    g = cuenca.to_crs(crs_metrico)
    geom = g.geometry.unary_union
    area_m2 = geom.area
    perimetro_m = geom.length
    area_km2 = area_m2 / 1e6
    perimetro_km = perimetro_m / 1000
    compacidad = perimetro_m / (2 * math.sqrt(math.pi * area_m2)) if area_m2 else None
    circularidad = 4 * math.pi * area_m2 / (perimetro_m ** 2) if perimetro_m else None

    axial_m, width_m = _rotated_rectangle_axes(geom)
    axial_km = axial_m / 1000.0 if axial_m else None
    width_km = width_m / 1000.0 if width_m else None
    factor_forma = area_km2 / (axial_km ** 2) if axial_km and axial_km > 0 else None
    indice_alargamiento = axial_km / width_km if axial_km and width_km and width_km > 0 else None

    drainage_length_km = None
    drainage_density = None
    stream_count = None
    stream_frequency = None
    if drainage is not None and not drainage.empty:
        d = drainage.to_crs(crs_metrico)
        drainage_length_km = float(d.geometry.length.sum() / 1000.0)
        drainage_density = drainage_length_km / area_km2 if area_km2 else None
        stream_count = int(len(d))
        stream_frequency = stream_count / area_km2 if area_km2 else None

    return {
        "area_km2": area_km2,
        "perimetro_km": perimetro_km,
        "coeficiente_compacidad": compacidad,
        "clasificacion_compacidad": _classify_compactness(compacidad),
        "relacion_circularidad": circularidad,
        "longitud_axial_km": axial_km,
        "ancho_maximo_km": width_km,
        "factor_forma": factor_forma,
        "clasificacion_factor_forma": _classify_form_factor(factor_forma),
        "indice_alargamiento": indice_alargamiento,
        "clasificacion_alargamiento": _classify_elongation(indice_alargamiento),
        "longitud_total_drenajes_km": drainage_length_km,
        "densidad_drenaje_km_km2": drainage_density,
        "clasificacion_densidad_drenaje": _classify_drainage_density(drainage_density),
        "numero_segmentos_drenaje": stream_count,
        "densidad_corrientes_n_km2": stream_frequency,
        "crs_calculo": str(crs_metrico),
    }
