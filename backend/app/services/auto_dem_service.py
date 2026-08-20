from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window, bounds as window_bounds
from rasterio.warp import transform_bounds

from app.services.opentopography_service import download_dem

ENGINE_ROOT = Path(__file__).resolve().parents[3] / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from hydrobasin_engine.dem import cargar_y_corregir_dem  # noqa: E402
from hydrobasin_engine.delineation import ajustar_punto_salida, delimitar_cuenca, transformar_punto  # noqa: E402
from hydrobasin_engine.hydrology import acumulacion_flujo, direccion_flujo  # noqa: E402

COARSE_SOURCE = "COP90"


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


def _mask_bounds_wgs84(mask, path: Path) -> dict[str, float] | None:
    basin = np.asarray(mask).astype(bool)
    rows, cols = np.where(basin)
    if rows.size == 0:
        return None
    row_min, row_max = int(rows.min()), int(rows.max())
    col_min, col_max = int(cols.min()), int(cols.max())
    window = Window(col_min, row_min, col_max - col_min + 1, row_max - row_min + 1)
    with rasterio.open(path) as src:
        left, bottom, right, top = window_bounds(window, src.transform)
        if src.crs is None:
            return None
        west, south, east, north = transform_bounds(
            src.crs, "EPSG:4326", left, bottom, right, top, densify_pts=21
        )
    return {"west": float(west), "south": float(south), "east": float(east), "north": float(north)}


def preliminary_watershed(path: Path, lng: float, lat: float) -> dict:
    with rasterio.open(path) as src:
        crs = src.crs.to_string() if src.crs else None
        if not crs:
            raise ValueError("El DEM descargado no tiene CRS.")
        pixel_area = abs(float(src.res[0] * src.res[1]))
        if src.crs and src.crs.is_projected and pixel_area > 0:
            snap_threshold = max(25.0, 1_000_000.0 / pixel_area)
        else:
            snap_threshold = 1000.0

    grid, corrected = cargar_y_corregir_dem(path)
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
        "basin_bounds": _mask_bounds_wgs84(mask, path),
    }


def expand_bounds(bounds: dict[str, float], touches: dict[str, bool], factor: float = 0.7) -> dict[str, float]:
    south, north, west, east = bounds["south"], bounds["north"], bounds["west"], bounds["east"]
    height = north - south
    width = east - west
    minor = 0.12
    return {
        "south": max(-89.9, south - height * (factor if touches.get("south") else minor)),
        "north": min(89.9, north + height * (factor if touches.get("north") else minor)),
        "west": max(-179.9, west - width * (factor if touches.get("west") else minor)),
        "east": min(179.9, east + width * (factor if touches.get("east") else minor)),
    }


def buffered_basin_bounds(bounds: dict[str, float], min_buffer_km: float = 10.0, ratio: float = 0.15) -> dict[str, float]:
    south, north, west, east = bounds["south"], bounds["north"], bounds["west"], bounds["east"]
    mean_lat = (south + north) / 2.0
    height_km = abs(north - south) * 111.32
    width_km = abs(east - west) * max(1.0, 111.32 * math.cos(math.radians(mean_lat)))
    buffer_km = max(min_buffer_km, max(height_km, width_km) * ratio)
    dlat = buffer_km / 111.32
    dlon = buffer_km / max(1.0, 111.32 * math.cos(math.radians(mean_lat)))
    return {
        "south": max(-89.9, south - dlat),
        "north": min(89.9, north + dlat),
        "west": max(-179.9, west - dlon),
        "east": min(179.9, east + dlon),
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
    final_verify_rounds: int = 2,
) -> tuple[Path, dict]:
    """Localiza la cuenca a 90 m y descarga/verifica el DEM final a la resolución elegida."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    bounds = initial_bounds(lat, lng, initial_radius_km)
    history: list[dict] = []
    coarse_path: Path | None = None
    coarse_check: dict | None = None

    for round_index in range(1, max_rounds + 1):
        if progress:
            progress(round_index, max_rounds, bounds, "coarse_downloading")
        candidate = destination_dir / f"coarse_round_{round_index}_{COARSE_SOURCE.lower()}.tif"
        await download_dem(
            source=COARSE_SOURCE,
            south=bounds["south"], north=bounds["north"], west=bounds["west"], east=bounds["east"],
            destination=candidate,
        )
        if coarse_path and coarse_path.exists():
            coarse_path.unlink(missing_ok=True)
        coarse_path = candidate

        if progress:
            progress(round_index, max_rounds, bounds, "coarse_checking")
        coarse_check = preliminary_watershed(candidate, lng, lat)
        history.append({"phase": "coarse", "round": round_index, "source": COARSE_SOURCE, "bounds": dict(bounds), **coarse_check})
        if coarse_check["contained"] and coarse_check.get("basin_bounds"):
            break
        bounds = expand_bounds(bounds, coarse_check["touches"])

    if not coarse_check or not coarse_check.get("basin_bounds"):
        raise RuntimeError("No fue posible estimar la extensión de la cuenca con el DEM preliminar de 90 m.")

    final_bounds = buffered_basin_bounds(coarse_check["basin_bounds"])
    if progress:
        progress(1, final_verify_rounds, final_bounds, "fine_downloading")

    final_candidate: Path | None = None
    fine_check: dict | None = None
    for verify_round in range(1, final_verify_rounds + 1):
        candidate = destination_dir / f"fine_round_{verify_round}_{source.lower()}.tif"
        await download_dem(
            source=source,
            south=final_bounds["south"], north=final_bounds["north"], west=final_bounds["west"], east=final_bounds["east"],
            destination=candidate,
        )
        if final_candidate and final_candidate.exists():
            final_candidate.unlink(missing_ok=True)
        final_candidate = candidate

        if progress:
            progress(verify_round, final_verify_rounds, final_bounds, "fine_checking")
        fine_check = preliminary_watershed(candidate, lng, lat)
        history.append({"phase": "fine", "round": verify_round, "source": source, "bounds": dict(final_bounds), **fine_check})
        if fine_check["contained"]:
            break
        final_bounds = expand_bounds(final_bounds, fine_check["touches"], factor=0.45)

    if final_candidate is None:
        raise RuntimeError("No fue posible descargar el DEM final.")

    final_path = destination_dir / f"hydrobasin_{source.lower()}_adaptive.tif"
    if final_path.exists():
        final_path.unlink()
    shutil.move(str(final_candidate), str(final_path))
    if coarse_path and coarse_path.exists():
        coarse_path.unlink(missing_ok=True)

    return final_path, {
        "bounds": final_bounds,
        "rounds": len([item for item in history if item["phase"] == "coarse"]),
        "fine_rounds": len([item for item in history if item["phase"] == "fine"]),
        "history": history,
        "contained": bool(fine_check and fine_check.get("contained")),
        "coarse_source": COARSE_SOURCE,
        "final_source": source,
        "coarse_basin_bounds": coarse_check.get("basin_bounds"),
    }
