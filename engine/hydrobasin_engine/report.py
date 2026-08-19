from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm


def _extent(grid):
    return grid.extent


def _sample(array, max_dim: int = 1400):
    data = np.asarray(array)
    rows, cols = data.shape[-2], data.shape[-1]
    step = max(1, int(np.ceil(max(rows, cols) / max_dim)))
    return data[::step, ::step]


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _focus_bounds(watershed, pad_ratio: float = 0.04):
    west, south, east, north = watershed.total_bounds
    dx = max(east - west, 1e-9)
    dy = max(north - south, 1e-9)
    return (
        west - dx * pad_ratio,
        south - dy * pad_ratio,
        east + dx * pad_ratio,
        north + dy * pad_ratio,
    )


def _focus(ax, bounds):
    west, south, east, north = bounds
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_aspect("equal", adjustable="box")


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
    subbasins=None,
) -> dict[str, str]:
    figures_dir = output_dir / "figuras"
    figures_dir.mkdir(parents=True, exist_ok=True)
    extent = _extent(grid)
    focus = _focus_bounds(watershed)

    dem_plot = _sample(dem)
    fig, ax = plt.subplots(figsize=(9, 6.2))
    im = ax.imshow(dem_plot, extent=extent, cmap="terrain")
    watershed.boundary.plot(ax=ax, linewidth=1.5)
    fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label="Elevación")
    ax.set_title("Contexto regional del modelo digital de elevación")
    ax.set_xlabel("Coordenada X")
    ax.set_ylabel("Coordenada Y")
    _save(fig, figures_dir / "01_dem_contexto.png")

    arr = _sample(corrected_dem).astype("float32", copy=False)
    gy, gx = np.gradient(arr)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(gx * gx + gy * gy))
    aspect = np.arctan2(-gx, gy)
    azimuth = np.deg2rad(315)
    altitude = np.deg2rad(45)
    hillshade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    hillshade = np.clip((hillshade + 1) / 2, 0, 1)

    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.imshow(hillshade, extent=extent, cmap="gray")
    watershed.boundary.plot(ax=ax, linewidth=1.8)
    _focus(ax, focus)
    ax.set_title("Relieve sombreado de la cuenca")
    ax.set_xlabel("Coordenada X")
    ax.set_ylabel("Coordenada Y")
    _save(fig, figures_dir / "02_hillshade_cuenca.png")

    acc = _sample(accumulation).astype("float32", copy=False)
    basin_sample = _sample(watershed_mask).astype(bool)
    acc_masked = np.where((acc > 0) & basin_sample, acc, np.nan)
    positive = acc_masked[np.isfinite(acc_masked)]
    vmax = float(positive.max()) if positive.size else 1.0
    fig, ax = plt.subplots(figsize=(9, 6.2))
    im = ax.imshow(acc_masked, extent=extent, cmap="viridis", norm=LogNorm(vmin=1, vmax=max(1, vmax)))
    watershed.boundary.plot(ax=ax, linewidth=1.4)
    _focus(ax, focus)
    fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label="Celdas aportantes (escala log)")
    ax.set_title("Acumulación de flujo dentro de la cuenca")
    ax.set_xlabel("Coordenada X")
    ax.set_ylabel("Coordenada Y")
    _save(fig, figures_dir / "03_acumulacion_cuenca.png")

    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.imshow(hillshade, extent=extent, cmap="gray", alpha=0.72)
    watershed.boundary.plot(ax=ax, linewidth=2.0)
    if drainage is not None and not drainage.empty:
        drainage.plot(ax=ax, linewidth=0.7)
    _focus(ax, focus)
    ax.set_title("Cuenca delimitada y red de drenaje")
    ax.set_xlabel("Coordenada X")
    ax.set_ylabel("Coordenada Y")
    _save(fig, figures_dir / "04_cuenca_drenaje.png")

    order = _sample(stream_order).astype("float32", copy=False)
    order_masked = np.where((order > 0) & basin_sample, order, np.nan)
    fig, ax = plt.subplots(figsize=(9, 6.2))
    im = ax.imshow(order_masked, extent=extent, cmap="viridis", interpolation="nearest")
    watershed.boundary.plot(ax=ax, linewidth=1.4)
    _focus(ax, focus)
    fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label="Orden de Strahler")
    ax.set_title("Jerarquía de la red — orden de Strahler")
    ax.set_xlabel("Coordenada X")
    ax.set_ylabel("Coordenada Y")
    _save(fig, figures_dir / "05_strahler_cuenca.png")

    figures = {
        "dem": "figuras/01_dem_contexto.png",
        "hillshade": "figuras/02_hillshade_cuenca.png",
        "accumulation": "figuras/03_acumulacion_cuenca.png",
        "watershed": "figuras/04_cuenca_drenaje.png",
        "strahler": "figuras/05_strahler_cuenca.png",
    }

    if subbasins is not None and not subbasins.empty:
        fig, ax = plt.subplots(figsize=(9, 6.2))
        ax.imshow(hillshade, extent=extent, cmap="gray", alpha=0.52)
        subbasins.plot(ax=ax, column="subbasin_id", cmap="tab20", alpha=0.46, edgecolor="white", linewidth=0.45)
        watershed.boundary.plot(ax=ax, linewidth=2.0)
        if drainage is not None and not drainage.empty:
            drainage.plot(ax=ax, linewidth=0.5)
        _focus(ax, focus)
        ax.set_title("Subcuencas hidrológicas dentro de la cuenca principal")
        ax.set_xlabel("Coordenada X")
        ax.set_ylabel("Coordenada Y")
        _save(fig, figures_dir / "06_subcuencas.png")
        figures["subbasins"] = "figuras/06_subcuencas.png"

    return figures


def _n(value, digits=2):
    return "N/D" if value is None else f"{value:.{digits}f}"


def _latex_escape(value) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _find_pdflatex() -> str | None:
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


def _subbasin_table_rows(subbasins) -> str:
    if subbasins is None or subbasins.empty or "area_km2" not in subbasins.columns:
        return ""
    top = subbasins.sort_values("area_km2", ascending=False).head(12)
    rows = []
    for _, row in top.iterrows():
        rows.append(f"{int(row['subbasin_id'])} & {_n(float(row['area_km2']), 2)} \\\\")
    return "\n".join(rows)


def _generar_fuente_latex(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None) -> str:
    tex_path = output_dir / "informe_hydrobasin.tex"
    resolution = summary.get("metric_resolution_m")
    resolution_text = "N/D" if not resolution else f"{resolution[0]:.1f} × {resolution[1]:.1f} m"
    outlet = summary.get("outlet_original", {})
    outlet_text = f"{outlet.get('y', 'N/D')}, {outlet.get('x', 'N/D')}"
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    subfigure = ""
    subtable = ""
    if figures.get("subbasins"):
        subfigure = rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{figures['subbasins']}}}
\caption{{Subcuencas hidrológicas derivadas de la red D8 dentro de la cuenca principal.}}
\label{{fig:subcuencas}}
\end{{figure}}
"""
        rows = _subbasin_table_rows(subbasins)
        if rows:
            subtable = rf"""
\subsection{{Subcuencas de mayor extensión}}
\begin{{table}}[H]
\centering
\begin{{tabular}}{{rr}}
\toprule
\textbf{{ID}} & \textbf{{Área (km$^2$)}} \\
\midrule
{rows}
\bottomrule
\end{{tabular}}
\caption{{Subcuencas de mayor extensión derivadas del DEM.}}
\end{{table}}
"""

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish,es-nodecimaldot]{{babel}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{geometry}}
\usepackage{{float}}
\usepackage{{microtype}}
\usepackage{{fancyhdr}}
\usepackage{{xcolor}}
\usepackage{{caption}}
\usepackage{{hyperref}}
\usepackage{{lastpage}}
\geometry{{top=2.2cm,bottom=2.1cm,left=2.5cm,right=2.5cm}}
\definecolor{{hydro}}{{HTML}}{{1F5F66}}
\definecolor{{hydrogray}}{{HTML}}{{5F6B72}}
\hypersetup{{colorlinks=true,linkcolor=hydro,urlcolor=hydro,pdfauthor={{HydroBasin Watershed Studio}},pdftitle={{Informe de delimitación y análisis de cuenca hidrográfica}}}}
\captionsetup{{font=small,labelfont=bf,labelsep=period}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.45em}}
\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{\small\textsc{{HydroBasin}}}}
\rhead{{\small Informe hidrográfico}}
\cfoot{{\small Página \thepage\ de \pageref{{LastPage}}}}
\renewcommand{{\headrulewidth}}{{0.4pt}}

\begin{{document}}

\begin{{titlepage}}
\thispagestyle{{empty}}
\vspace*{{1.4cm}}
{{\color{{hydro}}\Large\textbf{{HYDROBASIN}}}}\\[0.35cm]
{{\large Watershed Studio}}\\[2.0cm]
{{\Huge\bfseries Informe de delimitación y análisis de cuenca hidrográfica}}\\[0.7cm]
{{\large Caracterización morfométrica, red de drenaje, orden de Strahler y subcuencas}}\\[1.4cm]
\rule{{\textwidth}}{{0.8pt}}\\[0.8cm]
\begin{{tabular}}{{@{{}}p{{5.3cm}}p{{9.0cm}}@{{}}}}
\textbf{{Área delimitada}} & {_n(summary.get('area_km2'))} km$^2$ \\[0.28cm]
\textbf{{Exutorio seleccionado}} & {_latex_escape(outlet_text)} \\[0.28cm]
\textbf{{CRS de cálculo}} & {_latex_escape(summary.get('crs_calculo') or summary.get('crs_dem') or 'N/D')} \\[0.28cm]
\textbf{{Resolución aproximada}} & {_latex_escape(resolution_text)} \\[0.28cm]
\textbf{{Fecha de procesamiento}} & {generated_at} \\
\end{{tabular}}
\vfill
\rule{{\textwidth}}{{0.4pt}}\\[0.25cm]
{{\small Documento generado automáticamente por HydroBasin Watershed Studio.}}
\end{{titlepage}}

\tableofcontents
\listoffigures
\newpage

\section{{Objeto y alcance}}
El presente informe documenta la delimitación automática de la cuenca aportante al exutorio seleccionado y la caracterización de su estructura de drenaje a partir de un Modelo Digital de Elevación (DEM). Los resultados representan una interpretación hidrológica derivada del relieve, del algoritmo D8 y de los umbrales de análisis seleccionados.

\section{{Metodología de procesamiento}}
\subsection{{Acondicionamiento hidrológico del DEM}}
Se corrigieron depresiones cerradas, pits y zonas planas para obtener una superficie hidrológicamente continua antes del cálculo de direcciones de flujo.

\subsection{{Dirección y acumulación de flujo}}
La dirección de flujo se calculó mediante el esquema D8. Posteriormente se obtuvo la acumulación de flujo como número de celdas contribuyentes hacia cada posición del raster.

\subsection{{Exutorio y delimitación de la cuenca}}
El punto seleccionado por el usuario se ajustó a una celda cercana de alta acumulación. A partir de este exutorio se identificó la totalidad del área que drena hacia el punto de salida.

\subsection{{Red de drenaje, Strahler y subcuencas}}
La red se extrajo usando un umbral equivalente a {_n(summary.get('minimum_area_km2'), 3)} km$^2$ de área mínima aportante. La jerarquía se evaluó mediante el orden de Strahler y la cuenca principal se subdividió en unidades internas asociadas a confluencias y trayectorias de drenaje D8.

\section{{Resultados hidrológicos y morfométricos}}
\begin{{table}}[H]
\centering
\renewcommand{{\arraystretch}}{{1.25}}
\begin{{tabular}}{{p{{8.2cm}}r l}}
\toprule
\textbf{{Parámetro}} & \textbf{{Valor}} & \textbf{{Unidad}} \\
\midrule
Área de la cuenca & {_n(summary.get('area_km2'))} & km$^2$ \\
Perímetro & {_n(summary.get('perimetro_km'))} & km \\
Coeficiente de compacidad & {_n(summary.get('coeficiente_compacidad'), 3)} & -- \\
Relación de circularidad & {_n(summary.get('relacion_circularidad'), 3)} & -- \\
Área mínima de aporte & {_n(summary.get('minimum_area_km2'), 3)} & km$^2$ \\
Umbral de drenaje & {_n(summary.get('drainage_threshold'), 0)} & celdas \\
Orden máximo de Strahler & {summary.get('strahler_max', 'N/D')} & -- \\
Número de subcuencas & {summary.get('subbasin_count', 'N/D')} & -- \\
Resolución métrica aproximada & \multicolumn{{2}}{{l}}{{{_latex_escape(resolution_text)}}} \\
CRS de cálculo & \multicolumn{{2}}{{l}}{{{_latex_escape(summary.get('crs_calculo') or 'N/D')}}} \\
\bottomrule
\end{{tabular}}
\caption{{Síntesis de parámetros del análisis.}}
\end{{table}}

{subtable}

\section{{Cartografía técnica}}
\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{figures['dem']}}}
\caption{{Contexto regional del DEM y localización de la cuenca delimitada.}}
\label{{fig:dem}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{figures['hillshade']}}}
\caption{{Relieve sombreado de la cuenca.}}
\label{{fig:hillshade}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{figures['accumulation']}}}
\caption{{Acumulación de flujo dentro de la cuenca en escala logarítmica.}}
\label{{fig:acc}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{figures['watershed']}}}
\caption{{Cuenca principal y red de drenaje extraída.}}
\label{{fig:cuenca}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{figures['strahler']}}}
\caption{{Jerarquía de la red de drenaje según el orden de Strahler.}}
\label{{fig:strahler}}
\end{{figure}}
{subfigure}

\section{{Interpretación del umbral de drenaje}}
El área mínima de aporte controla la densidad de la red extraída. Valores menores permiten representar cauces potenciales de menor jerarquía, mientras que valores mayores conservan principalmente los drenajes estructurales. Por tanto, la red y las subcuencas obtenidas son dependientes de la escala del DEM y del umbral seleccionado.

\section{{Observaciones técnicas}}
Los límites presentados corresponden a resultados derivados del DEM y no sustituyen cartografía hidrográfica oficial. Para estudios de detalle se recomienda validar el exutorio, la red y las divisorias mediante cartografía de mayor resolución, información de campo y fuentes oficiales cuando estén disponibles.

\end{{document}}
"""
    tex_path.write_text(tex, encoding="utf-8")
    return tex_path.name


def _compile_latex(output_dir: Path, tex_name: str) -> dict:
    pdflatex = _find_pdflatex()
    pdf_path = output_dir / Path(tex_name).with_suffix(".pdf").name
    if not pdflatex:
        return {
            "compiled": False,
            "pdf": None,
            "compiler_found": False,
            "compiler_path": None,
            "compile_error": "HydroBasin no pudo localizar pdflatex en el PATH ni en las rutas habituales de MiKTeX.",
        }

    last_output = ""
    try:
        for _ in range(2):
            completed = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_name],
                cwd=output_dir,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            last_output = (completed.stdout or "") + "\n" + (completed.stderr or "")
            if completed.returncode != 0:
                lines = [line.strip() for line in last_output.splitlines() if line.strip()]
                detail = " | ".join(lines[-12:])[-2400:]
                return {
                    "compiled": False,
                    "pdf": None,
                    "compiler_found": True,
                    "compiler_path": pdflatex,
                    "compile_error": detail or f"pdflatex terminó con código {completed.returncode}.",
                }

        if not pdf_path.exists():
            return {
                "compiled": False,
                "pdf": None,
                "compiler_found": True,
                "compiler_path": pdflatex,
                "compile_error": "pdflatex terminó sin crear el archivo PDF esperado.",
            }

        return {
            "compiled": True,
            "pdf": pdf_path.name,
            "compiler_found": True,
            "compiler_path": pdflatex,
            "compile_error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "compiled": False,
            "pdf": None,
            "compiler_found": True,
            "compiler_path": pdflatex,
            "compile_error": "La compilación LaTeX superó 180 segundos. MiKTeX puede estar esperando instalar un paquete faltante.",
        }
    except Exception as exc:
        return {
            "compiled": False,
            "pdf": None,
            "compiler_found": True,
            "compiler_path": pdflatex,
            "compile_error": str(exc),
        }


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None) -> dict:
    """Genera la fuente LaTeX y compila el PDF oficial de HydroBasin con pdflatex."""
    tex_name = _generar_fuente_latex(output_dir, summary, figures, subbasins=subbasins)
    compile_result = _compile_latex(output_dir, tex_name)
    return {
        "tex": tex_name,
        "pdf": compile_result["pdf"],
        "compiled": compile_result["compiled"],
        "pdf_engine": "pdflatex",
        "compiler_found": compile_result["compiler_found"],
        "compiler_path": compile_result["compiler_path"],
        "compile_error": compile_result["compile_error"],
    }
