from __future__ import annotations

from pysheds.grid import Grid

D8 = (64, 128, 1, 2, 4, 8, 16, 32)


def direccion_flujo(grid: Grid, dem_corregido, dirmap=D8):
    return grid.flowdir(dem_corregido, dirmap=dirmap)


def acumulacion_flujo(grid: Grid, fdir, dirmap=D8):
    return grid.accumulation(fdir, dirmap=dirmap)


def extraer_red_mascara(accum, umbral: float):
    if umbral <= 0:
        raise ValueError("El umbral debe ser mayor que cero.")
    return accum >= umbral


def orden_strahler(grid: Grid, fdir, accum, umbral: float, dirmap=D8):
    """Calcula el orden de corrientes Strahler sobre la red definida por el umbral."""
    mask = extraer_red_mascara(accum, umbral)
    return grid.stream_order(fdir, mask, dirmap=dirmap)
