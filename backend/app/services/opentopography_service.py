from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import httpx

from app.core.config import settings

OPENTOPO_GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"


@dataclass(frozen=True)
class DemSource:
    id: str
    name: str
    resolution_m: int
    coverage: str
    kind: str
    note: str
    recommended_rank: int


GLOBAL_SOURCES: tuple[DemSource, ...] = (
    DemSource("COP30", "Copernicus GLO-30", 30, "global", "DSM", "30 m aprox.; producto global con edición hidrológica de cuerpos de agua y cauces.", 1),
    DemSource("NASADEM", "NASADEM", 30, "global", "DEM", "30 m aprox.; actualización del SRTM con reprocesamiento NASA.", 2),
    DemSource("SRTMGL1", "SRTM GL1", 30, "global", "DEM", "30 m aprox.; DEM global ampliamente utilizado en hidrología.", 3),
    DemSource("AW3D30", "ALOS World 3D", 30, "global", "DSM", "30 m aprox.; alternativa global derivada de ALOS.", 4),
    DemSource("COP90", "Copernicus GLO-90", 90, "global", "DSM", "90 m aprox.; menor detalle y menor peso de descarga.", 5),
    DemSource("SRTMGL3", "SRTM GL3", 90, "global", "DEM", "90 m aprox.; útil para áreas extensas o análisis regionales.", 6),
)


def _bbox_area_km2(south: float, north: float, west: float, east: float) -> float:
    # Aproximación suficiente para advertencias/estimaciones de descarga.
    mean_lat = (south + north) / 2.0
    km_lat = 111.32
    import math
    km_lon = 111.32 * max(0.01, math.cos(math.radians(mean_lat)))
    return abs(north - south) * km_lat * abs(east - west) * km_lon


def list_sources(south: float, north: float, west: float, east: float) -> dict:
    if south >= north or west >= east:
        raise ValueError("La extensión seleccionada no es válida.")
    if south < -90 or north > 90 or west < -180 or east > 180:
        raise ValueError("La extensión debe estar en coordenadas WGS84 válidas.")

    area_km2 = _bbox_area_km2(south, north, west, east)
    ordered: Iterable[DemSource] = sorted(GLOBAL_SOURCES, key=lambda s: (s.resolution_m, s.recommended_rank))
    sources = []
    for index, source in enumerate(ordered):
        data = asdict(source)
        data["recommended"] = index == 0
        data["estimated_cells"] = int(max(1, area_km2 * 1_000_000 / (source.resolution_m ** 2)))
        sources.append(data)

    return {
        "area_km2": area_km2,
        "recommended_source": sources[0]["id"],
        "sources": sources,
        "api_configured": bool(settings.opentopography_api_key),
    }


async def download_dem(
    *,
    source: str,
    south: float,
    north: float,
    west: float,
    east: float,
    destination: Path,
) -> Path:
    if not settings.opentopography_api_key:
        raise RuntimeError("OpenTopography no está configurado en el servidor. Define OPENTOPOGRAPHY_API_KEY en backend/.env.")

    valid_sources = {item.id for item in GLOBAL_SOURCES}
    if source not in valid_sources:
        raise ValueError(f"Fuente DEM no soportada: {source}")
    if south >= north or west >= east:
        raise ValueError("La extensión seleccionada no es válida.")

    params = {
        "demtype": source,
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": "GTiff",
        "API_Key": settings.opentopography_api_key,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0), follow_redirects=True) as client:
        response = await client.get(OPENTOPO_GLOBALDEM_URL, params=params)
        if response.status_code >= 400:
            detail = response.text.strip()[:1200]
            raise RuntimeError(f"OpenTopography respondió {response.status_code}: {detail or 'error sin detalle'}")
        content_type = response.headers.get("content-type", "").lower()
        if "text" in content_type or "json" in content_type:
            detail = response.text.strip()[:1200]
            raise RuntimeError(f"OpenTopography no devolvió un GeoTIFF: {detail or content_type}")
        destination.write_bytes(response.content)

    if destination.stat().st_size < 1024:
        raise RuntimeError("El archivo DEM descargado es demasiado pequeño y parece inválido.")
    return destination
