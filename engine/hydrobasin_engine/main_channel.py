from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
from rasterio.transform import rowcol, xy
from shapely.geometry import LineString

from .hydrology import D8


_DIRECTION_BY_OFFSET = {
    (-1, 0): D8[0],
    (-1, 1): D8[1],
    (0, 1): D8[2],
    (1, 1): D8[3],
    (1, 0): D8[4],
    (1, -1): D8[5],
    (0, -1): D8[6],
    (-1, -1): D8[7],
}

_NEIGHBOURS = tuple(_DIRECTION_BY_OFFSET.keys())


def _metric_crs_for_line(line: LineString, crs) -> str:
    gdf = gpd.GeoDataFrame({"geometry": [line]}, crs=crs)
    if gdf.crs is not None and gdf.crs.is_projected:
        return str(gdf.crs)
    centroid = gdf.to_crs(4326).geometry.iloc[0].centroid
    zone = int((centroid.x + 180) // 6) + 1
    epsg = 32600 + zone if centroid.y >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def _upstream_candidate(fdir: np.ndarray, accum: np.ndarray, basin: np.ndarray, r: int, c: int):
    rows, cols = fdir.shape
    candidates: list[tuple[float, int, int]] = []
    for dr, dc in _NEIGHBOURS:
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols or not basin[nr, nc]:
            continue
        target_offset = (-dr, -dc)
        expected = _DIRECTION_BY_OFFSET[target_offset]
        if int(fdir[nr, nc]) == int(expected):
            candidates.append((float(accum[nr, nc]), nr, nc))
    if not candidates:
        return None
    candidates.sort(reverse=True, key=lambda item: item[0])
    _, nr, nc = candidates[0]
    return nr, nc


def _find_viable_outlet_cell(fdir: np.ndarray, accum: np.ndarray, basin: np.ndarray, r: int, c: int, max_radius: int = 12):
    """Busca cerca del exutorio una celda de la cuenca que tenga conexión aguas arriba.

    El snap de Pysheds puede caer sobre el borde de la celda o en una celda terminal de la
    máscara. Para el cauce principal necesitamos empezar en una celda de la red que tenga
    al menos un vecino aportante. Se prioriza la mayor acumulación y la menor distancia.
    """
    rows, cols = basin.shape
    if 0 <= r < rows and 0 <= c < cols and basin[r, c] and _upstream_candidate(fdir, accum, basin, r, c) is not None:
        return r, c

    best = None
    for radius in range(1, max_radius + 1):
        r0, r1 = max(0, r - radius), min(rows, r + radius + 1)
        c0, c1 = max(0, c - radius), min(cols, c + radius + 1)
        for rr in range(r0, r1):
            for cc in range(c0, c1):
                if not basin[rr, cc]:
                    continue
                if _upstream_candidate(fdir, accum, basin, rr, cc) is None:
                    continue
                distance2 = (rr - r) ** 2 + (cc - c) ** 2
                score = (float(accum[rr, cc]), -distance2)
                if best is None or score > best[0]:
                    best = (score, rr, cc)
        if best is not None:
            return best[1], best[2]
    return None


def extraer_cauce_principal(
    flow_direction,
    accumulation,
    watershed_mask,
    corrected_dem,
    transform,
    crs,
    outlet_x: float,
    outlet_y: float,
) -> tuple[gpd.GeoDataFrame, dict]:
    """Traza el cauce principal desde el exutorio hacia la cabecera de mayor acumulación."""
    fdir = np.asarray(flow_direction)
    accum = np.asarray(accumulation)
    basin = np.asarray(watershed_mask).astype(bool, copy=False)
    dem = np.asarray(corrected_dem)

    r, c = rowcol(transform, outlet_x, outlet_y)
    r, c = int(r), int(c)
    if r < 0 or c < 0 or r >= basin.shape[0] or c >= basin.shape[1]:
        raise ValueError("El exutorio ajustado quedó fuera del DEM.")

    viable = _find_viable_outlet_cell(fdir, accum, basin, r, c)
    if viable is None:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=crs), {
            "main_channel_length_km": None,
            "main_channel_slope": None,
            "main_channel_slope_percent": None,
            "main_channel_elevation_outlet_m": None,
            "main_channel_elevation_source_m": None,
            "profile_distance_km": [],
            "profile_elevation_m": [],
        }

    r, c = viable
    cells: list[tuple[int, int]] = [(r, c)]
    visited = {(r, c)}
    max_steps = int(basin.sum())

    for _ in range(max_steps):
        candidate = _upstream_candidate(fdir, accum, basin, r, c)
        if candidate is None or candidate in visited:
            break
        r, c = candidate
        visited.add(candidate)
        cells.append(candidate)

    if len(cells) < 2:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=crs), {
            "main_channel_length_km": None,
            "main_channel_slope": None,
            "main_channel_slope_percent": None,
            "main_channel_elevation_outlet_m": None,
            "main_channel_elevation_source_m": None,
            "profile_distance_km": [],
            "profile_elevation_m": [],
        }

    coords = [xy(transform, rr, cc, offset="center") for rr, cc in cells]
    line = LineString(coords)
    channel = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs=crs)
    metric_crs = _metric_crs_for_line(line, crs)
    metric_line = channel.to_crs(metric_crs).geometry.iloc[0]
    length_m = float(metric_line.length)

    elevations = [float(dem[rr, cc]) for rr, cc in cells]
    source_z = elevations[-1]
    outlet_z = elevations[0]
    slope = max(0.0, (source_z - outlet_z) / length_m) if length_m > 0 else None

    metric_coords = list(metric_line.coords)
    distances = [0.0]
    cumulative = 0.0
    for p0, p1 in zip(metric_coords[:-1], metric_coords[1:]):
        cumulative += math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        distances.append(cumulative / 1000.0)

    return channel, {
        "main_channel_length_km": length_m / 1000.0,
        "main_channel_slope": slope,
        "main_channel_slope_percent": slope * 100.0 if slope is not None else None,
        "main_channel_elevation_outlet_m": outlet_z,
        "main_channel_elevation_source_m": source_z,
        "profile_distance_km": distances,
        "profile_elevation_m": elevations,
        "main_channel_metric_crs": metric_crs,
    }


def tiempos_concentracion(length_km: float | None, slope: float | None) -> dict:
    if not length_km or not slope or length_km <= 0 or slope <= 0:
        return {"tc_kirpich_h": None, "tc_temez_h": None, "tc_promedio_h": None}
    kirpich = 0.06628 * ((length_km / math.sqrt(slope)) ** 0.77)
    temez = 0.30 * ((length_km / (slope ** 0.25)) ** 0.76)
    return {
        "tc_kirpich_h": kirpich,
        "tc_temez_h": temez,
        "tc_promedio_h": (kirpich + temez) / 2.0,
    }
