from __future__ import annotations

import geopandas as gpd
from shapely.geometry import shape
from .hydrology import D8


def extraer_red_vectorial(grid, fdir, accum, umbral: float, crs=None, dirmap=D8):
    mask = accum >= umbral
    branches = grid.extract_river_network(fdir, mask, dirmap=dirmap)
    features = branches.get("features", []) if isinstance(branches, dict) else []
    if not features:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=crs)
    geoms = [shape(feat["geometry"]) for feat in features]
    props = [feat.get("properties", {}) for feat in features]
    return gpd.GeoDataFrame(props, geometry=geoms, crs=crs)
