from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.services.hydro_service import analyze_dem

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/watershed")
async def watershed_analysis(
    dem: UploadFile = File(...),
    x: float = Form(...),
    y: float = Form(...),
    point_crs: str = Form("EPSG:4326"),
    threshold: float = Form(1000),
):
    if not dem.filename or not dem.filename.lower().endswith((".tif", ".tiff")):
        raise HTTPException(status_code=400, detail="El DEM debe ser un GeoTIFF (.tif o .tiff).")
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
