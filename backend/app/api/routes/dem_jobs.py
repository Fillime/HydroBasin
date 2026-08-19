from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
from fastapi import APIRouter, HTTPException, Query
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds

from app.core.config import settings
from app.services.opentopography_service import download_dem

router = APIRouter(prefix="/analysis", tags=["analysis"])

_jobs: dict[str, dict] = {}


def _preview_from_path(path: Path) -> dict:
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError("El GeoTIFF no tiene un sistema de referencia (CRS) definido.")

        west, south, east, north = transform_bounds(
            src.crs, "EPSG:4326", *src.bounds, densify_pts=21
        )
        scale = min(1.0, 900 / max(src.width, src.height))
        preview_width = max(1, int(src.width * scale))
        preview_height = max(1, int(src.height * scale))
        band = src.read(
            1,
            out_shape=(preview_height, preview_width),
            masked=True,
            resampling=rasterio.enums.Resampling.bilinear,
        )
        valid = band.compressed().astype("float64")
        valid = valid[np.isfinite(valid)]
        if valid.size == 0:
            raise ValueError("El DEM no contiene valores de elevación válidos.")

        low, high = np.percentile(valid, [2, 98])
        if high <= low:
            low, high = float(valid.min()), float(valid.max())
        if high <= low:
            high = low + 1.0

        data = np.asarray(band.filled(low), dtype="float64")
        normalized = np.clip((data - low) / (high - low), 0, 1)
        image = (normalized * 255).astype("uint8")
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver="PNG",
                width=preview_width,
                height=preview_height,
                count=1,
                dtype="uint8",
            ) as dst:
                dst.write(image, 1)
            png_bytes = memory_file.read()

        return {
            "filename": path.name,
            "crs": src.crs.to_string(),
            "width": src.width,
            "height": src.height,
            "resolution": [abs(float(src.res[0])), abs(float(src.res[1]))],
            "bounds_native": {
                "west": float(src.bounds.left),
                "south": float(src.bounds.bottom),
                "east": float(src.bounds.right),
                "north": float(src.bounds.top),
            },
            "bounds_wgs84": {
                "west": float(west),
                "south": float(south),
                "east": float(east),
                "north": float(north),
            },
            "elevation_min": float(valid.min()),
            "elevation_max": float(valid.max()),
            "preview_data_url": "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii"),
        }


async def _run_download(job_id: str, source: str, south: float, north: float, west: float, east: float) -> None:
    job_dir = settings.workspace_dir / "dem_downloads" / job_id
    target = job_dir / f"hydrobasin_{source.lower()}_{job_id[:8]}.tif"
    _jobs[job_id].update({"status": "downloading", "message": "OpenTopography está preparando y transfiriendo el DEM…"})
    try:
        await download_dem(
            source=source,
            south=south,
            north=north,
            west=west,
            east=east,
            destination=target,
        )
        _jobs[job_id].update({"status": "processing", "message": "DEM recibido. Generando vista previa y metadatos…"})
        preview = await asyncio.to_thread(_preview_from_path, target)
        _jobs[job_id].update({
            "status": "ready",
            "message": "DEM listo para el análisis.",
            "dem_id": job_id,
            "source": source,
            "path": str(target),
            "size_bytes": target.stat().st_size,
            "preview": preview,
        })
    except Exception as exc:
        if target.exists():
            target.unlink(missing_ok=True)
        _jobs[job_id].update({"status": "error", "message": str(exc)})


@router.post("/dem-download-jobs")
async def start_dem_download(
    source: str = Query("COP30"),
    south: float = Query(...),
    north: float = Query(...),
    west: float = Query(...),
    east: float = Query(...),
):
    job_id = uuid4().hex
    _jobs[job_id] = {
        "status": "queued",
        "message": "Descarga en cola…",
        "dem_id": job_id,
        "source": source,
    }
    asyncio.create_task(_run_download(job_id, source, south, north, west, east))
    return {"job_id": job_id, "status": "queued"}


@router.get("/dem-download-jobs/{job_id}")
def dem_download_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        # Permite reutilizar un DEM listo incluso después de una recarga si el archivo sigue en workspace.
        job_dir = settings.workspace_dir / "dem_downloads" / job_id
        candidates = list(job_dir.glob("*.tif")) if job_dir.exists() else []
        if candidates:
            path = candidates[0]
            try:
                return {
                    "status": "ready",
                    "message": "DEM disponible en el servidor.",
                    "dem_id": job_id,
                    "size_bytes": path.stat().st_size,
                    "preview": _preview_from_path(path),
                }
            except Exception as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail="No existe esa descarga DEM.")
    return {key: value for key, value in job.items() if key != "path"}


def resolve_server_dem(dem_id: str) -> Path:
    job_dir = settings.workspace_dir / "dem_downloads" / dem_id
    candidates = list(job_dir.glob("*.tif")) if job_dir.exists() else []
    if not candidates:
        raise FileNotFoundError("El DEM descargado ya no está disponible en el servidor.")
    return candidates[0]
