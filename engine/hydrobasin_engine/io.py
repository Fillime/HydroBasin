from __future__ import annotations

from pathlib import Path
import geopandas as gpd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape
import numpy as np


def guardar_raster(ruta: str | Path, array, referencia: str | Path, nodata=None):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(referencia) as src:
        profile = src.profile.copy()
        data = np.asarray(array)
        profile.update(dtype=data.dtype, count=1)
        if nodata is not None:
            profile.update(nodata=nodata)
        with rasterio.open(ruta, "w", **profile) as dst:
            dst.write(data, 1)


def mascara_a_poligono(mask, referencia: str | Path):
    mask = np.asarray(mask).astype("uint8")
    with rasterio.open(referencia) as src:
        geoms = [shape(g) for g, value in shapes(mask, mask=mask.astype(bool), transform=src.transform) if value == 1]
        if not geoms:
            raise ValueError("La máscara de cuenca está vacía.")
        gdf = gpd.GeoDataFrame({"id": range(1, len(geoms) + 1)}, geometry=geoms, crs=src.crs)
        return gdf.dissolve().reset_index(drop=True)


def guardar_vector(gdf: gpd.GeoDataFrame, ruta: str | Path):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(ruta)
