from __future__ import annotations

from pathlib import Path
import rasterio
from pysheds.grid import Grid


def cargar_dem(ruta: str | Path):
    """Carga un DEM con pysheds y devuelve (grid, dem)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el DEM: {ruta}")
    grid = Grid.from_raster(str(ruta))
    dem = grid.read_raster(str(ruta))
    return grid, dem


def corregir_dem(grid: Grid, dem):
    """Corrige depresiones y zonas planas del DEM para análisis hidrológico."""
    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)
    return inflated


def metadatos_dem(ruta: str | Path) -> dict:
    with rasterio.open(ruta) as src:
        return {
            "crs": src.crs.to_string() if src.crs else None,
            "width": src.width,
            "height": src.height,
            "bounds": tuple(src.bounds),
            "resolution": src.res,
            "nodata": src.nodata,
            "dtype": src.dtypes[0],
        }
