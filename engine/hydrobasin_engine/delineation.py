from __future__ import annotations

from pyproj import CRS, Transformer
from pysheds.grid import Grid
from .hydrology import D8


def transformar_punto(x: float, y: float, crs_origen: str, crs_destino: str):
    if CRS.from_user_input(crs_origen) == CRS.from_user_input(crs_destino):
        return x, y
    transformer = Transformer.from_crs(crs_origen, crs_destino, always_xy=True)
    return transformer.transform(x, y)


def ajustar_punto_salida(grid: Grid, accum, x: float, y: float, umbral: float = 1000):
    mask = accum >= umbral
    x_snap, y_snap = grid.snap_to_mask(mask, (x, y))
    return float(x_snap), float(y_snap)


def delimitar_cuenca(grid: Grid, fdir, x: float, y: float, dirmap=D8):
    return grid.catchment(x=x, y=y, fdir=fdir, dirmap=dirmap, xytype="coordinate")
