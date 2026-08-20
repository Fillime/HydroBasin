from __future__ import annotations

import json
import queue
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.routes.dem_jobs import resolve_server_dem
from app.core.config import settings
from app.services.hydro_service import analyze_dem, recalculate_basin_from_job

router = APIRouter(prefix="/analysis", tags=["analysis"])
_executor = ThreadPoolExecutor(max_workers=2)


@router.post("/watershed-quick")
async def watershed_quick(
    source_job_id: str = Form(...),
    x: float = Form(...),
    y: float = Form(...),
    point_crs: str = Form("EPSG:4326"),
):
    """Recalcula únicamente la cuenca usando D8 y acumulación de un análisis previo."""
    if not source_job_id or any(ch not in "0123456789abcdefABCDEF" for ch in source_job_id):
        raise HTTPException(status_code=400, detail="El identificador del análisis base no es válido.")

    results_dir = settings.workspace_dir / source_job_id / "results"
    if not results_dir.exists():
        raise HTTPException(status_code=404, detail="No se encontró el análisis base para reutilizar sus resultados.")

    try:
        result = await __import__("asyncio").get_running_loop().run_in_executor(
            _executor,
            lambda: recalculate_basin_from_job(results_dir, x, y, point_crs),
        )
        return {"source_job_id": source_job_id, **result}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/watershed-stream")
async def watershed_stream(
    dem: UploadFile | None = File(None),
    dem_id: str | None = Form(None),
    x: float = Form(...),
    y: float = Form(...),
    point_crs: str = Form("EPSG:4326"),
    minimum_area_km2: float = Form(5.0),
    dem_source: str | None = Form(None),
):
    if not dem and not dem_id:
        raise HTTPException(status_code=400, detail="Debes cargar un DEM o seleccionar uno descargado en el servidor.")
    if dem and (not dem.filename or not dem.filename.lower().endswith((".tif", ".tiff"))):
        raise HTTPException(status_code=400, detail="El DEM debe ser un GeoTIFF (.tif o .tiff).")
    if minimum_area_km2 <= 0:
        raise HTTPException(status_code=400, detail="El área mínima de aporte debe ser mayor que cero.")

    job_id = uuid4().hex
    job_dir = settings.workspace_dir / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "results"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if dem_id:
        try:
            source_path = resolve_server_dem(dem_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        dem_path = input_dir / source_path.name
        try:
            dem_path.hardlink_to(source_path)
        except OSError:
            shutil.copy2(source_path, dem_path)
    else:
        assert dem is not None
        dem_path = input_dir / Path(dem.filename or "dem.tif").name
        dem_path.write_bytes(await dem.read())

    events: queue.Queue[dict] = queue.Queue()

    def progress(level: str, message: str, percent: int) -> None:
        events.put({"type": "log", "level": level, "message": message, "percent": percent})

    def run() -> None:
        try:
            progress("info", f"Proceso {job_id[:8]} iniciado.", 0)
            if dem_source:
                progress("info", f"Fuente DEM: {dem_source}.", 1)
            if dem_id:
                progress("ok", "Usando el DEM directamente desde el almacenamiento del backend; no se vuelve a transferir por el navegador.", 2)
            result = analyze_dem(
                dem_path=dem_path,
                x=x,
                y=y,
                point_crs=point_crs,
                threshold=None,
                minimum_area_km2=minimum_area_km2,
                dem_source=dem_source,
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
