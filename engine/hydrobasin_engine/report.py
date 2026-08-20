from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def _extent(grid):
    return grid.extent


def _sample(array, max_dim: int = 1400):
    data = np.asarray(array)
    rows, cols = data.shape[-2], data.shape[-1]
    step = max(1, int(np.ceil(max(rows, cols) / max_dim)))
    return data[::step, ::step]


def _save(fig, path: Path, dpi: int = 220):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _focus_bounds(watershed, pad_ratio: float = 0.04):
    west, south, east, north = watershed.total_bounds
    dx = max(east - west, 1e-9)
    dy = max(north - south, 1e-9)
    return west - dx * pad_ratio, south - dy * pad_ratio, east + dx * pad_ratio, north + dy * pad_ratio


def _focus(ax, bounds):
    west, south, east, north = bounds
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_aspect("equal", adjustable="box")


def _plot_profile(figures_dir: Path, summary: dict) -> str | None:
    distances = summary.get("profile_distance_km") or []
    elevations = summary.get("profile_elevation_m") or []
    if len(distances) < 2 or len(distances) != len(elevations):
        return None
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(distances, elevations, linewidth=1.8)
    ax.fill_between(distances, elevations, min(elevations), alpha=0.18)
    ax.set_title("Perfil longitudinal del cauce principal")
    ax.set_xlabel("Distancia desde el exutorio (km)")
    ax.set_ylabel("Elevación (m)")
    ax.grid(True, alpha=0.22)
    path = figures_dir / "07_perfil_cauce_principal.png"
    _save(fig, path)
    return "figuras/07_perfil_cauce_principal.png"


def _plot_plan(figures_dir: Path, watershed, drainage, subbasins, main_channel, summary: dict) -> str:
    metric_crs = summary.get("crs_calculo") or watershed.crs
    basin = watershed.to_crs(metric_crs)
    drains = drainage.to_crs(metric_crs) if drainage is not None and not drainage.empty else None
    subs = subbasins.to_crs(metric_crs) if subbasins is not None and not subbasins.empty else None
    channel = main_channel.to_crs(metric_crs) if main_channel is not None and not main_channel.empty else None

    fig, ax = plt.subplots(figsize=(12.8, 8.4))
    ax.set_facecolor("#f4f0df")
    if subs is not None:
        subs.plot(ax=ax, column="subbasin_id", cmap="Pastel2", alpha=0.72, edgecolor="#777777", linewidth=0.35)
    else:
        basin.plot(ax=ax, facecolor="#d8eee7", edgecolor="#333333", linewidth=1.2)
    basin.boundary.plot(ax=ax, color="#202020", linewidth=1.7)
    if drains is not None:
        drains.plot(ax=ax, color="#2775c9", linewidth=0.65, alpha=0.92)
    if channel is not None:
        channel.plot(ax=ax, color="#d62728", linewidth=2.1)

    west, south, east, north = basin.total_bounds
    dx, dy = east - west, north - south
    pad = 0.035
    ax.set_xlim(west - dx * pad, east + dx * pad)
    ax.set_ylim(south - dy * pad, north + dy * pad)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, color="#555555", linewidth=0.45, alpha=0.42)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("Coordenada Este")
    ax.set_ylabel("Coordenada Norte")
    ax.set_title("Plano hidrográfico - cuenca, subcuencas y red de drenaje", fontsize=14, fontweight="bold")

    ax.annotate("N", xy=(0.075, 0.92), xycoords="axes fraction", ha="center", va="center", fontsize=15, fontweight="bold")
    ax.annotate("", xy=(0.075, 0.89), xytext=(0.075, 0.78), xycoords="axes fraction", arrowprops=dict(arrowstyle="-|>", lw=2.0, color="#111111"))

    if dx > 0:
        raw_km = max(0.1, dx / 1000.0 * 0.20)
        exponent = 10 ** np.floor(np.log10(raw_km))
        normalized = raw_km / exponent
        nice = 1 if normalized < 1.5 else 2 if normalized < 3.5 else 5 if normalized < 7.5 else 10
        scale_km = nice * exponent
        x0 = west + dx * 0.06
        y0 = south + dy * 0.055
        x1 = x0 + scale_km * 1000.0
        ax.plot([x0, x1], [y0, y0], color="#111111", linewidth=5, solid_capstyle="butt")
        ax.plot([x0, x0], [y0 - dy * 0.008, y0 + dy * 0.008], color="#111111", linewidth=1)
        ax.plot([x1, x1], [y0 - dy * 0.008, y0 + dy * 0.008], color="#111111", linewidth=1)
        ax.text(x0, y0 + dy * 0.015, "0", fontsize=8, ha="center")
        ax.text(x1, y0 + dy * 0.015, f"{scale_km:g} km", fontsize=8, ha="center")

    legend = [
        Patch(facecolor="#d8eee7", edgecolor="#333333", label="Cuenca / subcuencas"),
        Line2D([0], [0], color="#2775c9", lw=1.2, label="Drenajes"),
        Line2D([0], [0], color="#d62728", lw=2.2, label="Cauce principal"),
    ]
    ax.legend(handles=legend, loc="lower right", frameon=True, framealpha=0.96, fontsize=9, title="LEYENDA")
    path = figures_dir / "08_plano_hidrografico.png"
    _save(fig, path, dpi=260)
    return "figuras/08_plano_hidrografico.png"


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
    main_channel=None,
    summary: dict | None = None,
) -> dict[str, str]:
    summary = summary or {}
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
    if main_channel is not None and not main_channel.empty:
        main_channel.plot(ax=ax, color="#d62728", linewidth=1.8)
    _focus(ax, focus)
    ax.set_title("Cuenca delimitada, red de drenaje y cauce principal")
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
    ax.set_title("Jerarquía de la red - orden de Strahler")
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
        if main_channel is not None and not main_channel.empty:
            main_channel.plot(ax=ax, color="#d62728", linewidth=1.6)
        _focus(ax, focus)
        ax.set_title("Subcuencas hidrológicas dentro de la cuenca principal")
        ax.set_xlabel("Coordenada X")
        ax.set_ylabel("Coordenada Y")
        _save(fig, figures_dir / "06_subcuencas.png")
        figures["subbasins"] = "figuras/06_subcuencas.png"

    profile = _plot_profile(figures_dir, summary)
    if profile:
        figures["profile"] = profile
    figures["plan"] = _plot_plan(figures_dir, watershed, drainage, subbasins, main_channel, summary)
    return figures


def _n(value, digits=2):
    return "N/D" if value is None else f"{value:.{digits}f}"


def _latex_escape(value) -> str:
    text = str(value)
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(ch, ch) for ch in text)


def _subbasin_table_rows(subbasins) -> str:
    if subbasins is None or subbasins.empty or "area_km2" not in subbasins.columns:
        return ""
    top = subbasins.sort_values("area_km2", ascending=False).head(12)
    return "\n".join(f"{int(row['subbasin_id'])} & {_n(float(row['area_km2']), 2)} \\\\" for _, row in top.iterrows())


def _interpretation(summary: dict) -> str:
    parts = []
    ff = summary.get("factor_forma")
    if ff is not None:
        parts.append(f"El factor de forma es {_n(ff, 3)} y la cuenca se clasifica como {_latex_escape(summary.get('clasificacion_factor_forma') or 'sin clasificación')}. Este índice describe la relación entre el área y la longitud axial, por lo que ayuda a interpretar la tendencia geométrica de la respuesta hidrológica.")
    kc = summary.get("coeficiente_compacidad")
    if kc is not None:
        parts.append(f"El índice de compacidad o Gravelius es {_n(kc, 3)}, con clasificación {_latex_escape(summary.get('clasificacion_compacidad') or 'sin clasificación')}. Valores más alejados de 1 indican formas progresivamente menos circulares.")
    dd = summary.get("densidad_drenaje_km_km2")
    if dd is not None:
        parts.append(f"La densidad de drenaje es {_n(dd, 3)} km/km$^2$ y se clasifica como {_latex_escape(summary.get('clasificacion_densidad_drenaje') or 'sin clasificación')}. Este parámetro expresa la longitud de cauces por unidad de superficie y depende del umbral usado para extraer la red.")
    slope = summary.get("main_channel_slope_percent")
    if slope is not None:
        parts.append(f"La pendiente media del cauce principal es {_n(slope, 2)}\%, parámetro empleado junto con su longitud para estimar tiempos de concentración por métodos empíricos.")
    return "\n\n".join(parts) or "Los indicadores deben interpretarse junto con la resolución y calidad del DEM, el umbral de drenaje y la ubicación del exutorio."


def _report_tex(summary: dict, figures: dict[str, str], subbasins) -> str:
    title = _latex_escape(summary.get("dem_source") or "HydroBasin")
    rows = _subbasin_table_rows(subbasins)
    sub_section = ""
    if rows:
        sub_section = rf"""
\subsection{{Subcuencas}}
Se identificaron {summary.get('subbasin_count', 0)} subcuencas hidrológicas mediante puntos de control derivados de la estructura de flujo D8. La tabla resume las unidades de mayor área.
\begin{{center}}
\begin{{tabular}}{{rr}}
\toprule
ID & Área (km$^2$) \\
\midrule
{rows}
\bottomrule
\end{{tabular}}
\end{{center}}
"""
    profile_figure = ""
    if figures.get("profile"):
        profile_figure = rf"""
\begin{{figure}}[H]
\centering\includegraphics[width=0.95\textwidth]{{{figures['profile']}}}
\caption{{Perfil longitudinal del cauce principal.}}
\end{{figure}}
"""
    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{xcolor}}
\geometry{{margin=2.2cm}}
\title{{Informe técnico de delimitación y análisis de cuenca}}
\author{{HydroBasin}}
\date{{{datetime.now().strftime('%Y-%m-%d %H:%M')}}}
\begin{{document}}
\maketitle
\section{{Objeto}}
Este documento resume el procesamiento automático ejecutado por HydroBasin a partir de un modelo digital de elevación y un exutorio. La fuente reportada para el DEM es \textbf{{{title}}}.

\section{{Metodología}}
El flujo aplicado comprende corrección hidrológica del DEM, dirección de flujo D8, acumulación, ajuste del exutorio a una celda de acumulación significativa, delimitación de cuenca, extracción de drenajes, orden de Strahler, subcuencas, cauce principal y parámetros morfométricos. El área mínima seleccionada para la red fue de {_n(summary.get('minimum_area_km2'), 3)} km$^2$, equivalente a {_n(summary.get('drainage_threshold'), 0)} celdas.

\section{{Resultados principales}}
\begin{{center}}
\begin{{tabular}}{{lr}}
\toprule
Parámetro & Resultado \\
\midrule
Área & {_n(summary.get('area_km2'))} km$^2$ \\
Perímetro & {_n(summary.get('perimetro_km'))} km \\
Longitud axial & {_n(summary.get('longitud_axial_km'))} km \\
Factor de forma & {_n(summary.get('factor_forma'), 3)} \\
Compacidad de Gravelius & {_n(summary.get('coeficiente_compacidad'), 3)} \\
Circularidad & {_n(summary.get('relacion_circularidad'), 3)} \\
Densidad de drenaje & {_n(summary.get('densidad_drenaje_km_km2'), 3)} km/km$^2$ \\
Orden Strahler máximo & {summary.get('strahler_max', 'N/D')} \\
Longitud cauce principal & {_n(summary.get('main_channel_length_km'))} km \\
Pendiente cauce principal & {_n(summary.get('main_channel_slope_percent'))}\% \\
Kirpich & {_n(summary.get('tc_kirpich_min'))} min \\
Témez & {_n(summary.get('tc_temez_min'))} min \\
Elevación mínima & {_n(summary.get('elevacion_min_m'))} m \\
Elevación máxima & {_n(summary.get('elevacion_max_m'))} m \\
Relieve & {_n(summary.get('relieve_cuenca_m'))} m \\
\bottomrule
\end{{tabular}}
\end{{center}}

{sub_section}
\section{{Cartografía}}
\begin{{figure}}[H]
\centering\includegraphics[width=0.95\textwidth]{{{figures['watershed']}}}
\caption{{Cuenca delimitada, red de drenaje y cauce principal.}}
\end{{figure}}
\begin{{figure}}[H]
\centering\includegraphics[width=0.95\textwidth]{{{figures['strahler']}}}
\caption{{Orden de corrientes de Strahler dentro de la cuenca.}}
\end{{figure}}
{profile_figure}
\section{{Interpretación}}
{_interpretation(summary)}

\section{{Limitaciones}}
HydroBasin no infiere precipitación, temperatura, caudal observado ni parámetros climáticos a partir del DEM. Los resultados dependen de la resolución y calidad del raster, del acondicionamiento hidrológico, de la ubicación del exutorio y del umbral de extracción de drenajes. Los tiempos de concentración son estimaciones empíricas y deben contrastarse con información del proyecto cuando se utilicen en diseño.
\end{{document}}
"""


def _plan_tex(summary: dict, figures: dict[str, str]) -> str:
    return rf"""\documentclass[10pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage[a3paper,landscape,margin=12mm]{{geometry}}
\usepackage{{graphicx}}
\usepackage{{array}}
\usepackage{{booktabs}}
\pagestyle{{empty}}
\begin{{document}}
\begin{{center}}
{{\Large\bfseries PLANO HIDROGRÁFICO DE CUENCA}}\\[1mm]
{{\small HydroBasin · CRS de cálculo: {_latex_escape(summary.get('crs_calculo') or 'N/D')}}}
\end{{center}}
\noindent
\begin{{minipage}}[t]{{0.78\textwidth}}
\centering\includegraphics[width=\linewidth,height=0.80\textheight,keepaspectratio]{{{figures['plan']}}}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.20\textwidth}}
\small
\textbf{{CUADRO TÉCNICO}}\\[2mm]
\begin{{tabular}}{{@{{}}p{{0.58\linewidth}}r@{{}}}}
\toprule
Área & {_n(summary.get('area_km2'))} km$^2$\\
Perímetro & {_n(summary.get('perimetro_km'))} km\\
Compacidad & {_n(summary.get('coeficiente_compacidad'),3)}\\
Circularidad & {_n(summary.get('relacion_circularidad'),3)}\\
Dens. drenaje & {_n(summary.get('densidad_drenaje_km_km2'),3)}\\
Strahler máx. & {summary.get('strahler_max','N/D')}\\
Subcuencas & {summary.get('subbasin_count','N/D')}\\
Cauce princ. & {_n(summary.get('main_channel_length_km'))} km\\
Pendiente & {_n(summary.get('main_channel_slope_percent'))}\%\\
Tc Kirpich & {_n(summary.get('tc_kirpich_min'))} min\\
Tc Témez & {_n(summary.get('tc_temez_min'))} min\\
\bottomrule
\end{{tabular}}\\[4mm]
\textbf{{Fuente DEM}}\\
{_latex_escape(summary.get('dem_source') or 'N/D')}\\[3mm]
\textbf{{Exutorio ajustado}}\\
{_latex_escape(summary.get('outlet_snapped') or 'N/D')}\\[3mm]
\textbf{{Nota}}\\
Resultados derivados del DEM y del umbral de drenaje seleccionado. Verificar contra información de campo y criterios del proyecto.
\end{{minipage}}
\end{{document}}
"""


def _find_tectonic() -> str | None:
    return shutil.which("tectonic") or shutil.which("tectonic.exe")


def _compile(tex_path: Path, output_dir: Path) -> tuple[Path | None, str | None]:
    compiler = _find_tectonic()
    if not compiler:
        return None, "Tectonic no está disponible en PATH."
    try:
        completed = subprocess.run(
            [compiler, tex_path.name, "--outdir", str(output_dir)],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    pdf_path = output_dir / f"{tex_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        detail = (completed.stderr or completed.stdout or "Error desconocido de compilación").strip()
        return None, detail[-1800:]
    return pdf_path, None


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None, main_channel=None) -> dict:
    tex_path = output_dir / "informe_hydrobasin.tex"
    plan_tex_path = output_dir / "plano_hidrografico.tex"
    tex_path.write_text(_report_tex(summary, figures, subbasins), encoding="utf-8")
    plan_tex_path.write_text(_plan_tex(summary, figures), encoding="utf-8")

    report_pdf, report_error = _compile(tex_path, output_dir)
    plan_pdf, plan_error = _compile(plan_tex_path, output_dir)
    errors = [error for error in (report_error, plan_error) if error]
    return {
        "tex": tex_path.name,
        "pdf": report_pdf.name if report_pdf else None,
        "plan_tex": plan_tex_path.name,
        "plan_pdf": plan_pdf.name if plan_pdf else None,
        "compiled": bool(report_pdf and plan_pdf),
        "compiler_found": bool(_find_tectonic()),
        "compile_error": " | ".join(errors) if errors else None,
    }
