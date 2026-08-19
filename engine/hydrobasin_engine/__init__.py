"""Motor geoespacial de HydroBasin."""

import numpy as np

# Compatibilidad temporal con dependencias que aún usan np.in1d.
# NumPy 2.4 eliminó este alias en favor de np.isin.
if not hasattr(np, "in1d"):
    np.in1d = np.isin  # type: ignore[attr-defined]

from .workflow import run_watershed_analysis

__all__ = ["run_watershed_analysis"]
