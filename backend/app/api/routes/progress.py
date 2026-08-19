from __future__ import annotations

import json
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.services.hydro_service import analyze_dem

router = APIRouter(prefix="/analysis", tags=["analysis"])
_executor = ThreadPoolExecutor(max_workers=2)


@router.post("/watershed-stream")
async def watershed_stream(
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
    events: queue.Queue[dict] = queue.Queue()

    def progress(level: str, message: str, percent: int) -> None:
        events.put({"type": "log", "level": level, "message": message, "percent": percent})

    def run() -> None:
        try:
            progress("info", f"Proceso {job_id[:8]} iniciado.", 0)
            result = analyze_dem(
                dem_path=dem_path,
                x=x,
                y=y,
                point_crs=point_crs,
                threshold=threshold,
                output_dir=output_dir,
                progress=progress,
            )
            events.put({"type": "result", "job_id": job_id, **result})
        except Exception as exc:
            events.put({"type": "error", "level": "error", "message": str(exc), "percent": 100})
        finally:
            events.put({"type": "done"})

    _executor.submit(run)

    def event_stream():
        while True:
            event = events.get()
            yield json.dumps(event, ensure_ascii=False) + "\n"
            if event.get("type") == "done":
                break

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )
