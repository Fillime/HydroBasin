from __future__ import annotations

import geopandas as gpd
import numpy as np
from numba import njit
from rasterio.features import shapes
from shapely.geometry import shape

from .hydrology import D8

_DROW = np.array([-1, -1, 0, 1, 1, 1, 0, -1], dtype=np.int8)
_DCOL = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype=np.int8)


@njit(cache=True)
def _downstream_indices(fdir_flat, rows, cols, dirmap):
    # int32 soporta holgadamente rásteres de decenas de millones de celdas
    # y reduce a la mitad la memoria frente a int64.
    n = rows * cols
    downstream = np.full(n, -1, dtype=np.int32)
    for idx in range(n):
        value = fdir_flat[idx]
        r = idx // cols
        c = idx - r * cols
        for k in range(8):
            if value == dirmap[k]:
                rr = r + _DROW[k]
                cc = c + _DCOL[k]
                if 0 <= rr < rows and 0 <= cc < cols:
                    downstream[idx] = rr * cols + cc
                break
    return downstream


@njit(cache=True)
def _stream_indegree(stream_flat, downstream):
    indegree = np.zeros(stream_flat.size, dtype=np.uint8)
    for idx in range(stream_flat.size):
        if not stream_flat[idx]:
            continue
        dst = downstream[idx]
        if dst >= 0 and stream_flat[dst]:
            indegree[dst] += 1
    return indegree


@njit(cache=True)
def _stream_targets(stream_flat, downstream, indegree):
    """Etiqueta cada celda de corriente por su primera confluencia u outlet aguas abajo."""
    n = stream_flat.size
    target_id = np.zeros(n, dtype=np.int32)
    next_id = 1

    for idx in range(n):
        if not stream_flat[idx]:
            continue
        dst = downstream[idx]
        is_outlet = dst < 0 or not stream_flat[dst]
        if indegree[idx] >= 2 or is_outlet:
            target_id[idx] = next_id
            next_id += 1

    for idx in range(n):
        if not stream_flat[idx] or target_id[idx] != 0:
            continue
        path = []
        cur = idx
        seen = 0
        while cur >= 0 and stream_flat[cur] and target_id[cur] == 0 and seen < n:
            path.append(cur)
            cur = downstream[cur]
            seen += 1
        label = target_id[cur] if cur >= 0 and cur < n else 0
        if label == 0:
            label = next_id
            next_id += 1
        for p in path:
            target_id[p] = label
    return target_id


@njit(cache=True)
def _assign_basin_labels(basin_flat, stream_flat, stream_labels, downstream):
    """Asigna cada celda de la cuenca al primer control de corriente aguas abajo."""
    n = basin_flat.size
    labels = np.zeros(n, dtype=np.int32)
    for idx in range(n):
        if stream_flat[idx]:
            labels[idx] = stream_labels[idx]

    for idx in range(n):
        if not basin_flat[idx] or labels[idx] != 0:
            continue
        path = []
        cur = idx
        seen = 0
        while cur >= 0 and basin_flat[cur] and labels[cur] == 0 and seen < n:
            path.append(cur)
            cur = downstream[cur]
            seen += 1
        label = labels[cur] if cur >= 0 and cur < n else 0
        for p in path:
            labels[p] = label
    return labels


def delimitar_subcuencas(
    fdir,
    accumulation,
    watershed_mask,
    transform,
    crs,
    threshold: float,
    dirmap=D8,
) -> tuple[np.ndarray, gpd.GeoDataFrame]:
    """
    Genera una partición no solapada de la cuenca principal usando confluencias
    y salidas de la red D8 como puntos de control. El resultado es una
    subdivisión derivada del DEM y del umbral, no una delimitación oficial.
    """
    basin = np.asarray(watershed_mask, dtype=bool)
    flow = np.asarray(fdir)
    acc = np.asarray(accumulation)
    stream = (acc >= threshold) & basin

    rows, cols = basin.shape
    downstream = _downstream_indices(flow.ravel(), rows, cols, np.asarray(dirmap))
    indegree = _stream_indegree(stream.ravel(), downstream)
    stream_labels = _stream_targets(stream.ravel(), downstream, indegree)
    labels = _assign_basin_labels(basin.ravel(), stream.ravel(), stream_labels, downstream).reshape(rows, cols)

    features = []
    for geom, value in shapes(labels, mask=labels > 0, transform=transform):
        features.append({"subbasin_id": int(value), "geometry": shape(geom)})

    if not features:
        return labels, gpd.GeoDataFrame({"subbasin_id": [], "geometry": []}, geometry="geometry", crs=crs)

    gdf = gpd.GeoDataFrame(features, geometry="geometry", crs=crs)
    gdf = gdf.dissolve(by="subbasin_id", as_index=False)
    metric = gdf.estimate_utm_crs() if gdf.crs and gdf.crs.is_geographic else gdf.crs
    if metric:
        gdf["area_km2"] = (gdf.to_crs(metric).geometry.area / 1e6).values
    return labels, gdf
