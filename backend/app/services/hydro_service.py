from __future__ import annotations

import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[3] / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from hydrobasin_engine.workflow import run_watershed_analysis  # noqa: E402


def analyze_dem(
    dem_path: Path,
    x: float,
    y: float,
    point_crs: str,
    threshold: float,
    output_dir: Path,
) -> dict:
    return run_watershed_analysis(
        dem_path=dem_path,
        x=x,
        y=y,
        point_crs=point_crs,
        output_dir=output_dir,
        drainage_threshold=threshold,
    )
