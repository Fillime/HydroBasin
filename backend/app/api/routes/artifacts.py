from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/jobs/{job_id}/artifact/{artifact_path:path}")
def download_artifact(job_id: str, artifact_path: str):
    if not job_id.isalnum():
        raise HTTPException(status_code=400, detail="Identificador de proceso inválido.")

    results_dir = (settings.workspace_dir / job_id / "results").resolve()
    requested = (results_dir / artifact_path).resolve()

    try:
        requested.relative_to(results_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Ruta de archivo inválida.") from exc

    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="El archivo solicitado no existe.")

    return FileResponse(requested, filename=requested.name)
