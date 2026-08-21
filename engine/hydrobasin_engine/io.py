from __future__ import annotations

import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union


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


def _rellenar_huecos_poligono(geom):
    """Elimina anillos interiores (huecos o islas internas) de un polígono o multipolígono."""
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    elif geom.geom_type == "MultiPolygon":
        polys = [Polygon(p.exterior) for p in geom.geoms if not p.is_empty]
        return unary_union(polys)
    elif geom.geom_type == "GeometryCollection":
        parts = []
        for g in geom.geoms:
            if g.geom_type in ("Polygon", "MultiPolygon"):
                parts.append(_rellenar_huecos_poligono(g))
        return unary_union(parts) if parts else geom
    return geom


def mascara_a_poligono(mask, referencia: str | Path):
    mask = np.asarray(mask).astype("uint8")
    with rasterio.open(referencia) as src:
        geoms = [shape(g) for g, value in shapes(mask, mask=mask.astype(bool), transform=src.transform) if value == 1]
        if not geoms:
            raise ValueError("La máscara de cuenca está vacía.")
        gdf = gpd.GeoDataFrame({"id": range(1, len(geoms) + 1)}, geometry=geoms, crs=src.crs)
        dissolved = gdf.dissolve().reset_index(drop=True)
        # Rellenar anillos interiores (huecos) no deseados generados por pits o discontinuidades
        dissolved["geometry"] = dissolved["geometry"].apply(_rellenar_huecos_poligono)
        return dissolved


def guardar_vector(gdf: gpd.GeoDataFrame, ruta: str | Path):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(ruta)


def guardar_shapefile_zip(gdf: gpd.GeoDataFrame, ruta_zip: str | Path, nombre: str) -> Path:
    """Exporta un GeoDataFrame como ESRI Shapefile y empaqueta todos sus archivos en ZIP."""
    ruta_zip = Path(ruta_zip).resolve()
    ruta_zip.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = ruta_zip.parent / f".{nombre}_shp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        shp_path = temp_dir / f"{nombre}.shp"
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")
        archive_base = ruta_zip.with_suffix("")
        created = Path(shutil.make_archive(str(archive_base), "zip", root_dir=temp_dir)).resolve()

        if created != ruta_zip:
            if ruta_zip.exists():
                ruta_zip.unlink()
            created.replace(ruta_zip)
        return ruta_zip
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
