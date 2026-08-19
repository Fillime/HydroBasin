from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio

from app.services.opentopography_service import download_dem

ENGINE_ROOT = Path(__file__).resolve().parents[3] / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from hydrobasin_engine.dem import cargar_dem, corregir_dem  # noqa: E402
from hydrobasin_engine.delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto  # noqa: E402
from hydrobasin_engine.hydrology import acumulacion_flujo, direccion_flujo  # noqa: E402


def initial_bounds(lat: float, lng: float, radius_km: float = 25.0) -> dict[str, float]:
    dlat = radius_km / 111.32
    dlon = radius_km / max(1.0, 111.32 * math.cos(math.radians(lat)))
    return {
        "south": max(-89.9, lat - dlat),
        "north": min(89.9, lat + dlat),
        "west": max(-179.9, lng - dlon),
        "east": min(179.9, lng + dlon),
    }


def _touching_edges(mask, margin: int = 3) -> dict[str, bool]:
    basin = np.asarray(mask).astype(bool)
    if basin.ndim != 2 or basin.size == 0:
        return {"north": False, "south": False, "west": False, "east": False}
    margin = max(1, min(margin, basin.shape[0] // 2, basin.shape[1] // 2))
    return {
        "north": bool(basin[:margin, :].any()),
        "south": bool(basin[-margin:, :].any()),
        "west": bool(basin[:, :margin].any()),
        "east": bool(basin[:, -margin:].any()),
    }


def preliminary_watershed(path: Path, lng: float, lat: float) -> dict:
    with rasterio.open(path) as src:
        crs = src.crs.to_string() if src.crs else None
        if not crs:
            raise ValueError("El DEM descargado no tiene CRS.")
        pixel_area = abs(float(src.res[0] * src.res[1]))
        # Para el ajuste preliminar usamos ~1 km² de aporte si el DEM está en metros;
        # en CRS geográfico se usa un umbral conservador fijo.
        if src.crs and src.crs.is_projected and pixel_area > 0:
            snap_threshold = max(25.0, 1_000_000.0 / pixel_area)
        else:
            snap_threshold = 1000.0

    grid, dem = cargar_dem(path)
    corrected = corregir_dem(grid, dem)
    fdir = direccion_flujo(grid, corrected)
    accum = acumulacion_flujo(grid, fdir)
    x_dem, y_dem = transformar_punto(lng, lat, "EPSG:4326", crs)
    x_snap, y_snap = ajustar_punto_salida(grid, accum, x_dem, y_dem, snap_threshold)
    mask = delimitar_cuenca(grid, fdir, x_snap, y_snap)
    edges = _touching_edges(mask)
    return {
        "touches": edges,
        "contained": not any(edges.values()),
        "cells": int(np.asarray(mask).astype(bool).sum()),
    }


def expand_bounds(bounds: dict[str, float], touches: dict[str, bool], factor: float = 0.7) -> dict[str, float]:
    south, north, west, east = bounds["south"], bounds["north"], bounds["west"], bounds["east"]
    height = north - south
    width = east - west
    # Si la divisoria toca un lado, ampliamos ese lado bastante; añadimos un margen menor
    # en los demás para evitar oscilaciones por cuencas diagonales.
    minor = 0.12
    return {
        "south": max(-89.9, south - height * (factor if touches.get("south") else minor)),
        "north": min(89.9, north + height * (factor if touches.get("north") else minor)),
        "west": max(-179.9, west - width * (factor if touches.get("west") else minor)),
        "east": min(179.9, east + width * (factor if touches.get("east") else minor)),
    }


async def obtain_adaptive_dem(
    *,
    source: str,
    lat: float,
    lng: float,
    destination_dir: Path,
    progress=None,
    initial_radius_km: float = 25.0,
    max_rounds: int = 5,
) -> tuple[Path, dict]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    bounds = initial_bounds(lat, lng, initial_radius_km)
    history = []
    last_path: Path | None = None

    for round_index in range(1, max_rounds + 1):
        if progress:
            progress(round_index, max_rounds, bounds, "downloading")
        candidate = destination_dir / f"adaptive_round_{round_index}_{source.lower()}.tif"
        await download_dem(
            source=source,
            south=bounds["south"],
            north=bounds["north"],
            west=bounds["west"],
            east=bounds["east"],
            destination=candidate,
        )
        if last_path and last_path.exists():
            last_path.unlink(missing_ok=True)
        last_path = candidate

        if progress:
            progress(round_index, max_rounds, bounds, "checking")
        check = preliminary_watershed(candidate, lng, lat)
        history.append({"round": round_index, "bounds": dict(bounds), **check})
        if check["contained"]:
            final_path = destination_dir / f"hydrobasin_{source.lower()}_adaptive.tif"
            if final_path.exists():
                final_path.unlink()
            shutil.move(str(candidate), str(final_path))
            return final_path, {
                "bounds": bounds,
                "rounds": round_index,
                "history": history,
                "contained": True,
            }
        bounds = expand_bounds(bounds, check["touches"])

    if last_path is None:
        raise RuntimeError("No fue posible obtener un DEM preliminar.")
    final_path = destination_dir / f"hydrobasin_{source.lower()}_adaptive.tif"
    if final_path.exists():
        final_path.unlink()
    shutil.move(str(last_path), str(final_path))
    return final_path, {
        "bounds": bounds,
        "rounds": max_rounds,
        "history": history,
        "contained": False,
    }
