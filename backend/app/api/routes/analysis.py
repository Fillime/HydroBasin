from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds

from app.core.config import settings
from app.services.hydro_service import analyze_dem
from app.services.opentopography_service import download_dem, list_sources

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _validate_dem(dem: UploadFile) -> None:
    if not dem.filename or not dem.filename.lower().endswith((".tif", ".tiff")):
        raise HTTPException(status_code=400, detail="El DEM debe ser un GeoTIFF (.tif o .tiff).")


@router.get("/dem-sources")
async def dem_sources(
    south: float = Query(...),
    north: float = Query(...),
    west: float = Query(...),
    east: float = Query(...),
):
    try:
        return list_sources(south, north, west, east)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/dem-download")
async def dem_download(
    source: str = Query("COP30"),
    south: float = Query(...),
    north: float = Query(...),
    west: float = Query(...),
    east: float = Query(...),
):
    download_id = uuid4().hex
    target_dir = settings.workspace_dir / "dem_downloads" / download_id
    target = target_dir / f"hydrobasin_{source.lower()}_{download_id[:8]}.tif"
    try:
        await download_dem(
            source=source,
            south=south,
            north=north,
            west=west,
            east=east,
            destination=target,
        )
        with rasterio.open(target) as src:
            if src.crs is None or src.width <= 0 or src.height <= 0:
                raise ValueError("OpenTopography devolvió un GeoTIFF inválido.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FileResponse(
        target,
        media_type="image/tiff",
        filename=target.name,
        headers={"X-HydroBasin-Dem-Source": source},
    )


@router.post("/dem-preview")
async def dem_preview(dem: UploadFile = File(...)):
    _validate_dem(dem)

    preview_id = uuid4().hex
    preview_dir = settings.workspace_dir / "previews" / preview_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    dem_path = preview_dir / Path(dem.filename).name
    dem_path.write_bytes(await dem.read())

    try:
        with rasterio.open(dem_path) as src:
            if src.crs is None:
                raise ValueError("El GeoTIFF no tiene un sistema de referencia (CRS) definido.")

            west, south, east, north = transform_bounds(
                src.crs,
                "EPSG:4326",
                *src.bounds,
                densify_pts=21,
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
                low = float(valid.min())
                high = float(valid.max())
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

            preview_data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

            return {
                "filename": dem.filename,
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
                "preview_data_url": preview_data_url,
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/watershed")
async def watershed_analysis(
    dem: UploadFile = File(...),
    x: float = Form(...),
    y: float = Form(...),
    point_crs: str = Form("EPSG:4326"),
    threshold: float = Form(1000),
):
    _validate_dem(dem)
    if threshold <= 0:
        raise HTTPException(status_code=400, detail="El umbral debe ser mayor que cero.")

    job_id = uuid4().hex
    job_dir = settings.workspace_dir / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "results"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    dem_path = input_dir / Path(dem.filename).name
    dem_path.write_bytes(await dem.read())

    try:
        result = analyze_dem(
            dem_path=dem_path,
            x=x,
            y=y,
            point_crs=point_crs,
            threshold=threshold,
            output_dir=output_dir,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"job_id": job_id, **result}
