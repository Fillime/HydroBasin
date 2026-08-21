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
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(distances, elevations, color="#1f9d8f", linewidth=2.2, label="Perfil altimétrico")
    min_elev = min(elevations)
    max_elev = max(elevations)
    ax.fill_between(distances, elevations, min_elev, color="#1f9d8f", alpha=0.15)
    
    # Anotaciones de puntos extremos
    ax.scatter([distances[0]], [elevations[0]], color="#ef4444", s=50, zorder=5)
    ax.annotate(f"Exutorio: {elevations[0]:.1f} m", (distances[0], elevations[0]),
                xytext=(8, 8), textcoords="offset points", fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#ef4444", lw=1))
    
    ax.scatter([distances[-1]], [elevations[-1]], color="#2563eb", s=50, zorder=5)
    ax.annotate(f"Cabecera: {elevations[-1]:.1f} m", (distances[-1], elevations[-1]),
                xytext=(-70, 8), textcoords="offset points", fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#2563eb", lw=1))

    slope_pct = summary.get("main_channel_slope_percent")
    length_km = summary.get("main_channel_length_km")
    info_text = f"Longitud: {length_km:.2f} km" if length_km else ""
    if slope_pct:
        info_text += f" | Pendiente media: {slope_pct:.2f}%"
    
    if info_text:
        ax.text(0.03, 0.92, info_text, transform=ax.transAxes, fontsize=9,
                verticalalignment="top", bbox=dict(boxstyle="round,pad=.3", fc="#f8fafc", ec="#cbd5e1", lw=1))

    ax.set_title("Perfil Longitudinal del Cauce Principal", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distancia acumulada desde el exutorio (km)", fontsize=9.5)
    ax.set_ylabel("Elevación (msnm)", fontsize=9.5)
    ax.grid(True, linestyle="--", alpha=0.35)
    path = figures_dir / "07_perfil_cauce_principal.png"
    _save(fig, path, dpi=220)
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
        channel.plot(ax=ax, color="#d62728", linewidth=2.2)

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
    ax.set_title("Plano hidrográfico - cuenca, subcuencas, drenajes y cauce principal", fontsize=14, fontweight="bold")

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
    flow_direction=None,
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

    basin_sample = _sample(watershed_mask).astype(bool)
    acc = _sample(accumulation).astype("float32", copy=False)
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
        main_channel.plot(ax=ax, color="#d62728", linewidth=1.9)
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
            main_channel.plot(ax=ax, color="#d62728", linewidth=1.7)
        _focus(ax, focus)
        ax.set_title("Subcuencas hidrológicas dentro de la cuenca principal")
        ax.set_xlabel("Coordenada X")
        ax.set_ylabel("Coordenada Y")
        _save(fig, figures_dir / "06_subcuencas.png")
        figures["subbasins"] = "figuras/06_subcuencas.png"

    if flow_direction is not None:
        fdir = _sample(flow_direction).astype("float32", copy=False)
        fdir_masked = np.where(basin_sample & (fdir > 0), fdir, np.nan)
        fig, ax = plt.subplots(figsize=(9, 6.2))
        im = ax.imshow(fdir_masked, extent=extent, cmap="twilight", interpolation="nearest")
        watershed.boundary.plot(ax=ax, linewidth=1.4)
        _focus(ax, focus)
        fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label="Código de dirección D8")
        ax.set_title("Dirección de flujo D8 dentro de la cuenca")
        ax.set_xlabel("Coordenada X")
        ax.set_ylabel("Coordenada Y")
        _save(fig, figures_dir / "09_direccion_flujo.png")
        figures["flow_direction"] = "figuras/09_direccion_flujo.png"

    profile = _plot_profile(figures_dir, summary)
    if profile:
        figures["profile"] = profile
    figures["plan"] = _plot_plan(figures_dir, watershed, drainage, subbasins, main_channel, summary)
    return figures


def _n(value, digits=2):
    if value is None:
        return "N/D"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _latex_escape(value) -> str:
    text = str(value)
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(ch, ch) for ch in text)


def _coord_pair(value) -> str:
    if not isinstance(value, dict):
        return "N/D"
    x, y = value.get("x"), value.get("y")
    if x is None or y is None:
        return "N/D"
    return f"{float(y):.6f}, {float(x):.6f}"


def _tc_minutes(summary: dict, key: str):
    value = summary.get(key)
    return None if value is None else float(value) * 60.0


def _subbasin_table_rows(subbasins) -> str:
    if subbasins is None or subbasins.empty or "area_km2" not in subbasins.columns:
        return ""
    top = subbasins.sort_values("area_km2", ascending=False).head(20)
    return "\n".join(f"{int(row['subbasin_id'])} & {_n(float(row['area_km2']), 2)} \\\\" for _, row in top.iterrows())


def _figure_block(figures: dict[str, str], key: str, caption: str, width: str = "0.94\\textwidth") -> str:
    path = figures.get(key)
    if not path:
        return ""
    return rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width={width}]{{{path}}}
\caption{{{caption}}}
\end{{figure}}
"""


def _interpretation(summary: dict) -> str:
    parts = []
    ff = summary.get("factor_forma")
    if ff is not None:
        parts.append(f"El factor de forma es {_n(ff, 3)} y la cuenca se clasifica como {_latex_escape(summary.get('clasificacion_factor_forma') or 'sin clasificación')}. Este índice expresa la relación entre el área de la cuenca y su longitud característica.")
    kc = summary.get("coeficiente_compacidad")
    if kc is not None:
        parts.append(f"El índice de compacidad de Gravelius es {_n(kc, 3)}, con clasificación {_latex_escape(summary.get('clasificacion_compacidad') or 'sin clasificación')}. Valores más alejados de 1 representan geometrías progresivamente menos circulares.")
    dd = summary.get("densidad_drenaje_km_km2")
    if dd is not None:
        parts.append(f"La densidad de drenaje es {_n(dd, 3)} km/km$^2$ y se clasifica como {_latex_escape(summary.get('clasificacion_densidad_drenaje') or 'sin clasificación')}. Este valor depende directamente del umbral de área mínima empleado para extraer la red.")
    if summary.get("main_channel_length_km") is not None:
        parts.append(rf"El cauce principal presenta una longitud aproximada de {_n(summary.get('main_channel_length_km'))} km y una pendiente media de {_n(summary.get('main_channel_slope_percent'), 2)}\%. Estos parámetros se utilizan para caracterizar la trayectoria principal de evacuación del flujo y estimar tiempos de concentración.")
    return "\n\n".join(parts) or "Los indicadores deben interpretarse conjuntamente con la calidad del DEM, el umbral de drenaje y la posición del exutorio."


def _report_tex(summary: dict, figures: dict[str, str], subbasins) -> str:
    source = _latex_escape(summary.get("dem_source") or "N/D")
    original_coord = _coord_pair(summary.get("outlet_original"))
    snapped_coord = _coord_pair(summary.get("outlet_snapped"))
    original_crs = _latex_escape((summary.get("outlet_original") or {}).get("crs", "N/D"))
    snapped_crs = _latex_escape((summary.get("outlet_snapped") or {}).get("crs", "N/D"))
    resolution = summary.get("metric_resolution_m")
    resolution_text = "N/D" if not resolution else f"{float(resolution[0]):.1f} x {float(resolution[1]):.1f} m"
    rows = _subbasin_table_rows(subbasins)
    sub_table = ""
    if rows:
        sub_table = rf"""
\begin{{table}}[H]
\centering
\caption{{Subcuencas de mayor área.}}
\begin{{tabular}}{{rr}}
\toprule
ID & Área (km$^2$) \\
\midrule
{rows}
\bottomrule
\end{{tabular}}
\end{{table}}
"""

    main_channel_available = summary.get("main_channel_length_km") is not None
    if main_channel_available:
        main_channel_text = rf"""
\begin{{table}}[H]
\centering
\begin{{tabular}}{{lr}}
\toprule
Parámetro & Resultado \\
\midrule
Longitud del cauce principal & {_n(summary.get('main_channel_length_km'))} km \\
Elevación en cabecera & {_n(summary.get('main_channel_elevation_source_m'))} m \\
Elevación en exutorio & {_n(summary.get('main_channel_elevation_outlet_m'))} m \\
Desnivel & {_n((summary.get('main_channel_elevation_source_m') or 0) - (summary.get('main_channel_elevation_outlet_m') or 0))} m \\
Pendiente media & {_n(summary.get('main_channel_slope_percent'), 3)}\% \\
Tiempo de concentración Kirpich & {_n(_tc_minutes(summary, 'tc_kirpich_h'))} min \\
Tiempo de concentración Témez & {_n(_tc_minutes(summary, 'tc_temez_h'))} min \\
Tiempo de concentración promedio & {_n(_tc_minutes(summary, 'tc_promedio_h'))} min \\
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    else:
        main_channel_text = "No fue posible establecer un cauce principal continuo con la topología D8 obtenida. El análisis conserva la red de drenaje completa y este resultado debe revisarse antes de utilizar tiempos de concentración."

    cartography = "".join([
        _figure_block(figures, "dem", "Contexto regional del modelo digital de elevación y cuenca delimitada."),
        _figure_block(figures, "hillshade", "Relieve sombreado dentro de la cuenca."),
        _figure_block(figures, "flow_direction", "Dirección de flujo calculada mediante el esquema D8."),
        _figure_block(figures, "accumulation", "Acumulación de flujo y concentración del aporte aguas arriba."),
        _figure_block(figures, "watershed", "Cuenca principal, red de drenaje y cauce principal."),
        _figure_block(figures, "strahler", "Jerarquía de corrientes según el orden de Strahler."),
        _figure_block(figures, "subbasins", "Subcuencas hidrológicas internas y red de drenaje."),
        _figure_block(figures, "profile", "Perfil longitudinal del cauce principal."),
    ])

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{xcolor}}
\usepackage{{array}}
\usepackage{{fancyhdr}}
\usepackage{{microtype}}
\geometry{{margin=2.2cm}}
\definecolor{{hb}}{{HTML}}{{1F6F78}}
\definecolor{{hbsoft}}{{HTML}}{{EEF6F6}}
\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{HydroBasin}}
\rhead{{Informe de análisis hidrográfico}}
\cfoot{{\thepage}}
\begin{{document}}

\begin{{titlepage}}
\vspace*{{2.0cm}}
{{\color{{hb}}\Large\bfseries HYDROBASIN / WATERSHED STUDIO}}\\[0.6cm]
{{\Huge\bfseries Informe de delimitación y análisis de cuenca hidrográfica}}\\[0.5cm]
{{\large Análisis hidrológico derivado de Modelo Digital de Elevación}}\\[1.5cm]
\renewcommand{{\arraystretch}}{{1.35}}
\begin{{tabular}}{{p{{5.2cm}}p{{9.0cm}}}}
\toprule
\textbf{{Dato}} & \textbf{{Información}} \\
\midrule
Fuente del DEM & {source} \\
Coordenadas del exutorio original & {original_coord} ({original_crs}) \\
Coordenadas del exutorio ajustado & {snapped_coord} ({snapped_crs}) \\
CRS del DEM & {_latex_escape(summary.get('crs_dem') or 'N/D')} \\
CRS de cálculo & {_latex_escape(summary.get('crs_calculo') or summary.get('crs_dem') or 'N/D')} \\
Resolución métrica aproximada & {resolution_text} \\
Área delimitada & {_n(summary.get('area_km2'))} km$^2$ \\
Fecha de procesamiento & {datetime.now().strftime('%d/%m/%Y %H:%M')} \\
\bottomrule
\end{{tabular}}
\vfill
\noindent\colorbox{{hbsoft}}{{\parbox{{0.94\textwidth}}{{Documento técnico generado automáticamente. Los resultados dependen de la resolución y calidad del DEM, del acondicionamiento hidrológico y de los parámetros seleccionados para la extracción de drenajes.}}}}
\end{{titlepage}}

\tableofcontents
\newpage

\section{{Objeto y alcance}}
El presente informe documenta la delimitación de la cuenca hidrográfica aportante al exutorio seleccionado y la caracterización de su respuesta geométrica e hidrológica a partir del DEM. Se incluyen el acondicionamiento del terreno, dirección y acumulación de flujo, red de drenaje, orden de Strahler, subcuencas, cauce principal, perfil longitudinal y parámetros morfométricos.

\section{{Datos de entrada y referencia espacial}}
\begin{{tabular}}{{p{{6.2cm}}p{{8.2cm}}}}
\toprule
Fuente DEM & {source} \\
Dimensiones del DEM & {summary.get('dem_width', 'N/D')} x {summary.get('dem_height', 'N/D')} celdas \\
CRS DEM & {_latex_escape(summary.get('crs_dem') or 'N/D')} \\
Resolución & {resolution_text} \\
Exutorio original & {original_coord} \\
Exutorio ajustado & {snapped_coord} \\
Área mínima de aporte & {_n(summary.get('minimum_area_km2'), 3)} km$^2$ \\
Umbral equivalente & {_n(summary.get('drainage_threshold'), 0)} celdas \\
\bottomrule
\end{{tabular}}

\section{{Metodología de procesamiento}}
\subsection{{Acondicionamiento hidrológico del DEM}}
Se corrigen pits, depresiones y zonas planas para obtener una superficie hidrológicamente conectada sin modificar la resolución espacial del raster.
\subsection{{Dirección y acumulación de flujo}}
La dirección de flujo se determina mediante el esquema D8 y la acumulación representa el número de celdas aportantes aguas arriba de cada posición.
\subsection{{Exutorio y delimitación de cuenca}}
El punto suministrado se ajusta a una celda de acumulación significativa. A partir del exutorio ajustado se delimita la cuenca principal.
\subsection{{Red de drenaje y orden de Strahler}}
La red se extrae con el área mínima de aporte seleccionada y se jerarquiza mediante el orden de Strahler.
\subsection{{Subcuencas}}
Las subcuencas se obtienen a partir de la estructura de flujo D8 y puntos de control asociados a confluencias y salidas internas de la red.
\subsection{{Cauce principal}}
El cauce principal se traza desde el exutorio hacia la cabecera siguiendo la conectividad de flujo. A partir de su longitud y desnivel se obtiene la pendiente media y se estiman tiempos de concentración empíricos.

\section{{Resultados hidrológicos y morfométricos}}
\begin{{table}}[H]
\centering
\begin{{tabular}}{{p{{8.0cm}}r}}
\toprule
Parámetro & Resultado \\
\midrule
Área & {_n(summary.get('area_km2'))} km$^2$ \\
Perímetro & {_n(summary.get('perimetro_km'))} km \\
Longitud axial & {_n(summary.get('longitud_axial_km'))} km \\
Factor de forma & {_n(summary.get('factor_forma'), 3)} \\
Compacidad de Gravelius & {_n(summary.get('coeficiente_compacidad'), 3)} \\
Relación de circularidad & {_n(summary.get('relacion_circularidad'), 3)} \\
Densidad de drenaje & {_n(summary.get('densidad_drenaje_km_km2'), 3)} km/km$^2$ \\
Orden máximo de Strahler & {summary.get('strahler_max', 'N/D')} \\
Número de subcuencas & {summary.get('subbasin_count', 'N/D')} \\
Elevación mínima & {_n(summary.get('elevacion_min_m'))} m \\
Elevación máxima & {_n(summary.get('elevacion_max_m'))} m \\
Elevación media & {_n(summary.get('elevacion_media_m'))} m \\
Relieve total & {_n(summary.get('relieve_cuenca_m'))} m \\
\bottomrule
\end{{tabular}}
\end{{table}}

\section{{Cauce principal y tiempo de concentración}}
{main_channel_text}
{_figure_block(figures, 'profile', 'Perfil longitudinal del cauce principal.')}

\section{{Subcuencas}}
Se identificaron \textbf{{{summary.get('subbasin_count', 0)}}} subcuencas hidrológicas dentro de la cuenca principal. Estas unidades permiten interpretar la distribución espacial de aportes y la organización interna del drenaje.
{sub_table}
{_figure_block(figures, 'subbasins', 'Subcuencas hidrológicas internas, red de drenaje y cauce principal.')}

\section{{Cartografía técnica}}
{cartography}

\section{{Interpretación}}
{_interpretation(summary)}

\section{{Criterio de extracción de drenajes}}
El área mínima de aporte controla la densidad de la red. Valores pequeños incorporan cauces potenciales de menor jerarquía; valores mayores conservan principalmente los drenajes estructurales. Su selección debe responder a la resolución del DEM, escala de presentación y objetivo del estudio.

\section{{Limitaciones}}
HydroBasin no infiere precipitación, temperatura, caudal observado ni parámetros climáticos a partir del DEM. Los resultados dependen de la resolución y calidad del raster, del acondicionamiento hidrológico, de la ubicación del exutorio y del umbral de drenaje. Los tiempos de concentración son estimaciones empíricas y deben contrastarse con información del proyecto cuando se utilicen en diseño.
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
{{\small HydroBasin · CRS de cálculo: {_latex_escape(summary.get('crs_calculo') or summary.get('crs_dem') or 'N/D')}}}
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
Tc Kirpich & {_n(_tc_minutes(summary, 'tc_kirpich_h'))} min\\
Tc Témez & {_n(_tc_minutes(summary, 'tc_temez_h'))} min\\
\bottomrule
\end{{tabular}}\\[4mm]
\textbf{{Fuente DEM}}\\
{_latex_escape(summary.get('dem_source') or 'N/D')}\\[3mm]
\textbf{{Exutorio original}}\\
{_coord_pair(summary.get('outlet_original'))}\\[2mm]
\textbf{{Exutorio ajustado}}\\
{_coord_pair(summary.get('outlet_snapped'))}\\[3mm]
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
    work_dir = tex_path.parent.resolve()
    resolved_output_dir = output_dir.resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [compiler, tex_path.name, "--outdir", str(resolved_output_dir)],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    pdf_path = resolved_output_dir / f"{tex_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        detail = (completed.stderr or completed.stdout or "Error desconocido de compilación").strip()
        return None, detail[-1800:]
    return pdf_path, None


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None, main_channel=None) -> dict:
    from .report_professional import generar_informes as _generar_informes_pro
    return _generar_informes_pro(output_dir, summary, figures, subbasins=subbasins, main_channel=main_channel)
