from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm


def _extent(grid):
    return grid.extent


def _sample(array, max_dim: int = 1200):
    data = np.asarray(array)
    rows, cols = data.shape[-2], data.shape[-1]
    step = max(1, int(np.ceil(max(rows, cols) / max_dim)))
    return data[::step, ::step]


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _find_pdflatex() -> str | None:
    """Encuentra pdflatex incluso cuando Uvicorn no hereda el PATH actualizado de Windows."""
    found = shutil.which("pdflatex")
    if found:
        return found

    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")

    if local_app_data:
        root = Path(local_app_data)
        candidates.extend([
            root / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / "pdflatex.exe",
            root / "MiKTeX" / "miktex" / "bin" / "x64" / "pdflatex.exe",
        ])
    if program_files:
        candidates.append(Path(program_files) / "MiKTeX" / "miktex" / "bin" / "x64" / "pdflatex.exe")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "MiKTeX" / "miktex" / "bin" / "pdflatex.exe")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def generar_figuras(
    output_dir: Path,
    grid,
    dem,
    corrected_dem,
    accumulation,
    watershed_mask,
    stream_order,
    watershed,
    drainage,
) -> dict[str, str]:
    figures_dir = output_dir / "figuras"
    figures_dir.mkdir(parents=True, exist_ok=True)
    extent = _extent(grid)

    dem_plot = _sample(dem)
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(dem_plot, extent=extent, cmap="terrain")
    fig.colorbar(im, ax=ax, label="Elevación")
    ax.set_title("Modelo digital de elevación")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    _save(fig, figures_dir / "01_dem.png")

    arr = _sample(corrected_dem).astype("float32", copy=False)
    gy, gx = np.gradient(arr)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(gx * gx + gy * gy))
    aspect = np.arctan2(-gx, gy)
    azimuth = np.deg2rad(315)
    altitude = np.deg2rad(45)
    hillshade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    hillshade = np.clip((hillshade + 1) / 2, 0, 1)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(hillshade, extent=extent, cmap="gray")
    ax.set_title("Relieve sombreado")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    _save(fig, figures_dir / "02_hillshade.png")

    acc = _sample(accumulation).astype("float32", copy=False)
    positive = acc[acc > 0]
    vmax = float(positive.max()) if positive.size else 1.0
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(np.where(acc > 0, acc, np.nan), extent=extent, cmap="viridis", norm=LogNorm(vmin=1, vmax=max(1, vmax)))
    fig.colorbar(im, ax=ax, label="Celdas aportantes (escala log)")
    ax.set_title("Acumulación de flujo")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    _save(fig, figures_dir / "03_acumulacion.png")

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(hillshade, extent=extent, cmap="gray", alpha=0.75)
    watershed.boundary.plot(ax=ax, linewidth=2)
    if drainage is not None and not drainage.empty:
        drainage.plot(ax=ax, linewidth=0.8)
    ax.set_title("Cuenca delimitada y red de drenaje")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    _save(fig, figures_dir / "04_cuenca_drenaje.png")

    order = _sample(stream_order).astype("float32", copy=False)
    fig, ax = plt.subplots(figsize=(8, 6))
    masked = np.where(order > 0, order, np.nan)
    im = ax.imshow(masked, extent=extent, cmap="viridis")
    fig.colorbar(im, ax=ax, label="Orden de Strahler")
    ax.set_title("Orden de corrientes de Strahler")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    _save(fig, figures_dir / "05_strahler.png")

    return {
        "dem": "figuras/01_dem.png",
        "hillshade": "figuras/02_hillshade.png",
        "accumulation": "figuras/03_acumulacion.png",
        "watershed": "figuras/04_cuenca_drenaje.png",
        "strahler": "figuras/05_strahler.png",
    }


def generar_informe_latex(output_dir: Path, summary: dict, figures: dict[str, str]) -> dict:
    tex_path = output_dir / "informe_hydrobasin.tex"
    area = summary.get("area_km2")
    perimeter = summary.get("perimetro_km")
    max_order = summary.get("strahler_max")
    threshold_area = summary.get("minimum_area_km2")
    crs = str(summary.get("crs_calculo") or summary.get("crs_dem") or "N/D")

    def n(value, digits=2):
        return "N/D" if value is None else f"{value:.{digits}f}"

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{geometry}}
\usepackage{{float}}
\usepackage{{hyperref}}
\geometry{{margin=2.5cm}}
\title{{Informe de delimitación y análisis de cuenca hidrográfica}}
\author{{HydroBasin}}
\date{{\today}}
\begin{{document}}
\maketitle

\section{{Objetivo}}
Delimitar la cuenca aportante al exutorio seleccionado a partir de un Modelo Digital de Elevación (DEM), calcular la dirección y acumulación de flujo, extraer la red de drenaje y caracterizar su jerarquía mediante el orden de Strahler.

\section{{Metodología}}
El flujo de procesamiento comprende: acondicionamiento hidrológico del DEM, dirección de flujo D8, acumulación de flujo, ajuste del exutorio a la red de mayor acumulación, delimitación de la cuenca, extracción de drenajes y cálculo del orden de Strahler.

\section{{Resultados principales}}
\begin{{table}}[H]
\centering
\begin{{tabular}}{{lll}}
\toprule
Parámetro & Valor & Unidad \\
\midrule
Área de la cuenca & {n(area)} & km$^2$ \\
Perímetro & {n(perimeter)} & km \\
Área mínima de aporte & {n(threshold_area, 3)} & km$^2$ \\
Orden máximo de Strahler & {max_order if max_order is not None else 'N/D'} & -- \\
Sistema de referencia de cálculo & \multicolumn{{2}}{{l}}{{{crs}}} \\
\bottomrule
\end{{tabular}}
\caption{{Parámetros principales de la cuenca.}}
\end{{table}}

\section{{Cartografía del análisis}}
\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figures['dem']}}}
\caption{{Modelo digital de elevación.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figures['hillshade']}}}
\caption{{Relieve sombreado del terreno.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figures['accumulation']}}}
\caption{{Acumulación de flujo en escala logarítmica.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figures['watershed']}}}
\caption{{Límite de la cuenca y red de drenaje.}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figures['strahler']}}}
\caption{{Orden de corrientes de Strahler.}}
\end{{figure}}

\section{{Observación sobre el umbral de drenaje}}
El área mínima de aporte controla la densidad de la red extraída. Valores menores generan una red más detallada, mientras que valores mayores conservan principalmente los cauces de mayor jerarquía. Este parámetro debe seleccionarse de acuerdo con la escala del estudio y la resolución del DEM.

\end{{document}}
"""
    tex_path.write_text(tex, encoding="utf-8")

    pdf_path = output_dir / "informe_hydrobasin.pdf"
    pdflatex = _find_pdflatex()
    compiled = False
    compile_error: str | None = None

    if pdflatex:
        try:
            completed = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                cwd=output_dir,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            compiled = completed.returncode == 0 and pdf_path.exists()
            if not compiled:
                output = (completed.stdout or "") + "\n" + (completed.stderr or "")
                lines = [line.strip() for line in output.splitlines() if line.strip()]
                compile_error = " | ".join(lines[-8:])[-1800:] or f"pdflatex terminó con código {completed.returncode}."
        except subprocess.TimeoutExpired:
            compile_error = "La compilación de LaTeX superó el tiempo máximo de 120 segundos. MiKTeX puede estar esperando instalar un paquete faltante."
        except Exception as exc:
            compile_error = str(exc)

    return {
        "tex": tex_path.name,
        "pdf": pdf_path.name if compiled else None,
        "compiled": compiled,
        "compiler_found": bool(pdflatex),
        "compiler_path": pdflatex,
        "compile_error": compile_error,
    }
