from __future__ import annotations

import gc
from pathlib import Path

import rasterio
from pyproj import CRS, Geod, Transformer
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


def cargar_y_corregir_dem(ruta: str | Path):
    """Carga y acondiciona un DEM liberando cada etapa tan pronto deja de ser necesaria.

    Esta ruta evita que el DEM original, el relleno de pits y el relleno de depresiones
    permanezcan vivos simultáneamente durante todo el acondicionamiento. No cambia la
    resolución ni remuestrea el raster.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el DEM: {ruta}")

    grid = Grid.from_raster(str(ruta))
    dem = grid.read_raster(str(ruta))

    pit_filled = grid.fill_pits(dem)
    del dem
    gc.collect()

    flooded = grid.fill_depressions(pit_filled)
    del pit_filled
    gc.collect()

    corrected = grid.resolve_flats(flooded)
    del flooded
    gc.collect()

    return grid, corrected


def metadatos_dem(ruta: str | Path) -> dict:
    with rasterio.open(ruta) as src:
        return {
            "crs": src.crs.to_string() if src.crs else None,
            "width": src.width,
            "height": src.height,
            "bounds": tuple(src.bounds),
            "resolution": src.res,
            "transform": src.transform,
            "nodata": src.nodata,
            "dtype": src.dtypes[0],
        }


def resolucion_metrica_aproximada(ruta: str | Path) -> tuple[float, float]:
    """Devuelve el tamaño aproximado del píxel en metros en el centro del DEM."""
    with rasterio.open(ruta) as src:
        if src.crs is None:
            raise ValueError("El DEM no tiene CRS definido.")
        crs = CRS.from_user_input(src.crs)
        rx, ry = abs(float(src.res[0])), abs(float(src.res[1]))
        if crs.is_projected:
            unit_factor = 1.0
            if crs.axis_info and crs.axis_info[0].unit_conversion_factor:
                unit_factor = float(crs.axis_info[0].unit_conversion_factor)
            return rx * unit_factor, ry * unit_factor

        cx = (src.bounds.left + src.bounds.right) / 2
        cy = (src.bounds.bottom + src.bounds.top) / 2
        transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(cx, cy)
        geod = Geod(ellps="WGS84")
        _, _, width_m = geod.inv(lon - rx / 2, lat, lon + rx / 2, lat)
        _, _, height_m = geod.inv(lon, lat - ry / 2, lon, lat + ry / 2)
        return abs(float(width_m)), abs(float(height_m))


def umbral_celdas_desde_area(ruta: str | Path, area_km2: float) -> tuple[int, tuple[float, float]]:
    """Convierte un área mínima de aporte en km² a número de celdas del DEM."""
    if area_km2 <= 0:
        raise ValueError("El área mínima de aporte debe ser mayor que cero.")
    width_m, height_m = resolucion_metrica_aproximada(ruta)
    cell_area = width_m * height_m
    if cell_area <= 0:
        raise ValueError("No fue posible calcular el área de la celda del DEM.")
    threshold = max(1, round(area_km2 * 1_000_000 / cell_area))
    return int(threshold), (width_m, height_m)
