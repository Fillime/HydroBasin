from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

ENGINE_ROOT = Path(__file__).resolve().parents[3] / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

# Mantener el generador de figuras del motor y sustituir solamente la plantilla
# documental antes de que workflow enlace generar_informes.
import hydrobasin_engine.report as report_module  # noqa: E402
from hydrobasin_engine.fast_delineation import recalculate_watershed_from_cache  # noqa: E402
from hydrobasin_engine.report_professional import generar_informes as generar_informes_professional  # noqa: E402

report_module.generar_informes = generar_informes_professional

from hydrobasin_engine.workflow import run_watershed_analysis  # noqa: E402


def analyze_dem(
    dem_path: Path,
    x: float,
    y: float,
    point_crs: str,
    threshold: float | None,
    output_dir: Path,
    minimum_area_km2: float | None = None,
    dem_source: str | None = None,
    project_name: str | None = None,
    client: str | None = None,
    calculated_by: str | None = None,
    reviewed_by: str | None = None,
    progress: Callable[[str, str, int], None] | None = None,
) -> dict:
    return run_watershed_analysis(
        dem_path=dem_path,
        x=x,
        y=y,
        point_crs=point_crs,
        output_dir=output_dir,
        drainage_threshold=threshold,
        minimum_area_km2=minimum_area_km2,
        dem_source=dem_source,
        project_name=project_name,
        client=client,
        calculated_by=calculated_by,
        reviewed_by=reviewed_by,
        progress=progress,
    )


def recalculate_basin_from_job(results_dir: Path, x: float, y: float, point_crs: str = "EPSG:4326") -> dict:
    return recalculate_watershed_from_cache(
        results_dir=results_dir,
        x=x,
        y=y,
        point_crs=point_crs,
    )


def reprocess_analysis(
    results_dir: Path,
    mode: str,
    x: float,
    y: float,
    point_crs: str = "EPSG:4326",
    minimum_area_km2: float = 5.0,
    project_name: str | None = None,
    client: str | None = None,
    calculated_by: str | None = None,
    reviewed_by: str | None = None,
    progress: Callable[[str, str, int], None] | None = None,
) -> dict:
    from hydrobasin_engine.reprocess import reprocess_stage
    return reprocess_stage(
        results_dir=results_dir,
        mode=mode,
        x=x,
        y=y,
        point_crs=point_crs,
        minimum_area_km2=minimum_area_km2,
        project_name=project_name,
        client=client,
        calculated_by=calculated_by,
        reviewed_by=reviewed_by,
        progress=progress,
    )

