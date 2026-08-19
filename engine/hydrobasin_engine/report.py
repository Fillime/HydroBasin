from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

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

    # North arrow.
    ax.annotate("N", xy=(0.075, 0.92), xycoords="axes fraction", ha="center", va="center", fontsize=15, fontweight="bold")
    ax.annotate("", xy=(0.075, 0.89), xytext=(0.075, 0.78), xycoords="axes fraction", arrowprops=dict(arrowstyle="-|>", lw=2.0, color="#111111"))

    # Approximate graphic scale in projected metric coordinates.
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
        parts.append(f"La pendiente media global del cauce principal es {_n(slope, 2)}\%, calculada entre la cabecera trazada automáticamente y el exutorio. Debe interpretarse junto con el perfil longitudinal, pues no reemplaza un análisis por tramos.")
    return "\n\n".join(parts)


def _generar_fuente_latex(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None) -> str:
    tex_path = output_dir / "informe_hydrobasin.tex"
    resolution = summary.get("metric_resolution_m")
    resolution_text = "N/D" if not resolution else f"{resolution[0]:.1f} × {resolution[1]:.1f} m"
    outlet = summary.get("outlet_original", {})
    outlet_text = f"{outlet.get('y', 'N/D')}, {outlet.get('x', 'N/D')}"
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    sub_rows = _subbasin_table_rows(subbasins)
    sub_table = rf"""\subsection{{Subcuencas de mayor extensión}}
\begin{{table}}[H]\centering\begin{{tabular}}{{rr}}\toprule\textbf{{ID}} & \textbf{{Área (km$^2$)}} \\\midrule
{sub_rows}
\bottomrule\end{{tabular}}\caption{{Subcuencas de mayor extensión derivadas del DEM.}}\end{{table}}""" if sub_rows else ""
    profile_figure = rf"""\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['profile']}}}\caption{{Perfil longitudinal automático del cauce principal, medido desde el exutorio hacia la cabecera.}}\end{{figure}}""" if figures.get("profile") else ""
    sub_figure = rf"""\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['subbasins']}}}\caption{{Subcuencas hidrológicas derivadas de la red D8.}}\end{{figure}}""" if figures.get("subbasins") else ""

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish,es-nodecimaldot]{{babel}}
\usepackage{{graphicx,booktabs,array,geometry,float,microtype,fancyhdr,xcolor,caption,hyperref,lastpage}}
\geometry{{top=2.0cm,bottom=2.0cm,left=2.2cm,right=2.2cm}}
\definecolor{{hydro}}{{HTML}}{{1F5F66}}
\definecolor{{hydrolight}}{{HTML}}{{EAF3F2}}
\hypersetup{{colorlinks=true,linkcolor=hydro,urlcolor=hydro}}
\captionsetup{{font=small,labelfont=bf,labelsep=period}}
\setlength{{\parindent}}{{0pt}}\setlength{{\parskip}}{{0.45em}}
\pagestyle{{fancy}}\fancyhf{{}}\lhead{{\small\textsc{{HydroBasin}}}}\rhead{{\small Informe de caracterización hidrográfica}}\cfoot{{\small Página \thepage\ de \pageref{{LastPage}}}}
\begin{{document}}
\begin{{titlepage}}\thispagestyle{{empty}}\vspace*{{1.2cm}}
{{\color{{hydro}}\Large\textbf{{HYDROBASIN}}}}\\[0.3cm]{{\large Watershed Studio}}\\[1.7cm]
{{\Huge\bfseries Informe de caracterización hidrográfica y morfométrica}}\\[0.55cm]
{{\large Cuenca principal, subcuencas, red de drenaje y cauce principal}}\\[1.1cm]\rule{{\textwidth}}{{0.8pt}}\\[0.7cm]
\begin{{tabular}}{{@{{}}p{{5.2cm}}p{{9.3cm}}@{{}}}}
\textbf{{Área delimitada}} & {_n(summary.get('area_km2'))} km$^2$ \\[0.22cm]
\textbf{{Fuente del DEM}} & {_latex_escape(summary.get('dem_source') or 'N/D')} \\[0.22cm]
\textbf{{Exutorio}} & {_latex_escape(outlet_text)} \\[0.22cm]
\textbf{{CRS de cálculo}} & {_latex_escape(summary.get('crs_calculo') or summary.get('crs_dem') or 'N/D')} \\[0.22cm]
\textbf{{Resolución aproximada}} & {_latex_escape(resolution_text)} \\[0.22cm]
\textbf{{Fecha de procesamiento}} & {generated_at} \\
\end{{tabular}}\vfill
{{\small Resultados derivados automáticamente del DEM y de los parámetros definidos en HydroBasin.}}
\end{{titlepage}}
\tableofcontents\listoffigures\newpage

\section{{Información básica y alcance}}
El análisis delimita la cuenca aportante al exutorio seleccionado y caracteriza su geometría, relieve y red de drenaje. Los límites, cauces y subcuencas son resultados derivados del DEM; no sustituyen cartografía hidrográfica oficial ni observaciones de campo.

\begin{{table}}[H]\centering\begin{{tabular}}{{p{{7.2cm}}p{{7.2cm}}}}\toprule
\textbf{{Dato}} & \textbf{{Valor}} \\\midrule
Fuente del DEM & {_latex_escape(summary.get('dem_source') or 'N/D')} \\
CRS del DEM & {_latex_escape(summary.get('crs_dem') or 'N/D')} \\
CRS métrico de cálculo & {_latex_escape(summary.get('crs_calculo') or 'N/D')} \\
Resolución métrica aproximada & {_latex_escape(resolution_text)} \\
Área mínima de aporte & {_n(summary.get('minimum_area_km2'), 3)} km$^2$ \\
Orden máximo de Strahler & {summary.get('strahler_max', 'N/D')} \\
Subcuencas derivadas & {summary.get('subbasin_count', 'N/D')} \\
\bottomrule\end{{tabular}}\caption{{Información básica del procesamiento.}}\end{{table}}

\section{{Metodología}}
El DEM se acondicionó mediante corrección de depresiones y zonas planas. La dirección y acumulación de flujo se calcularon con el esquema D8. El exutorio fue ajustado a una celda de alta acumulación; desde allí se delimitó la cuenca, se extrajo la red de drenaje, se calculó el orden de Strahler y se subdividió la cuenca en unidades internas. El cauce principal se trazó desde el exutorio hacia la cabecera seleccionando sucesivamente el tributario aguas arriba con mayor acumulación.

\section{{Índices morfométricos relacionados con la forma}}
\begin{{table}}[H]\centering\renewcommand{{\arraystretch}}{{1.22}}\begin{{tabular}}{{p{{6.2cm}}r p{{5.2cm}}}}\toprule
\textbf{{Parámetro}} & \textbf{{Valor}} & \textbf{{Clasificación / unidad}} \\\midrule
Área & {_n(summary.get('area_km2'))} & km$^2$ \\
Perímetro & {_n(summary.get('perimetro_km'))} & km \\
Longitud axial & {_n(summary.get('longitud_axial_km'))} & km \\
Ancho máximo aproximado & {_n(summary.get('ancho_maximo_km'))} & km \\
Factor de forma & {_n(summary.get('factor_forma'), 3)} & {_latex_escape(summary.get('clasificacion_factor_forma') or 'N/D')} \\
Índice de compacidad / Gravelius & {_n(summary.get('coeficiente_compacidad'), 3)} & {_latex_escape(summary.get('clasificacion_compacidad') or 'N/D')} \\
Índice de alargamiento & {_n(summary.get('indice_alargamiento'), 3)} & {_latex_escape(summary.get('clasificacion_alargamiento') or 'N/D')} \\
Relación de circularidad & {_n(summary.get('relacion_circularidad'), 3)} & adimensional \\
\bottomrule\end{{tabular}}\caption{{Índices asociados a la forma de la cuenca.}}\end{{table}}

\section{{Red de drenaje}}
\begin{{table}}[H]\centering\begin{{tabular}}{{p{{7cm}}r p{{4.6cm}}}}\toprule
\textbf{{Parámetro}} & \textbf{{Valor}} & \textbf{{Unidad / clasificación}} \\\midrule
Longitud total de drenajes & {_n(summary.get('longitud_total_drenajes_km'))} & km \\
Densidad de drenaje & {_n(summary.get('densidad_drenaje_km_km2'), 3)} & km/km$^2$ - {_latex_escape(summary.get('clasificacion_densidad_drenaje') or 'N/D')} \\
Segmentos de drenaje & {summary.get('numero_segmentos_drenaje', 'N/D')} & unidades \\
Densidad de corrientes & {_n(summary.get('densidad_corrientes_n_km2'), 3)} & segmentos/km$^2$ \\
Orden máximo de Strahler & {summary.get('strahler_max', 'N/D')} & orden \\
\bottomrule\end{{tabular}}\caption{{Parámetros de la red de drenaje.}}\end{{table}}

\section{{Relieve, cauce principal y tiempo de concentración}}
\begin{{table}}[H]\centering\begin{{tabular}}{{p{{7cm}}r p{{4.4cm}}}}\toprule
\textbf{{Parámetro}} & \textbf{{Valor}} & \textbf{{Unidad}} \\\midrule
Elevación mínima & {_n(summary.get('elevacion_min_m'), 1)} & m \\
Elevación media & {_n(summary.get('elevacion_media_m'), 1)} & m \\
Elevación máxima & {_n(summary.get('elevacion_max_m'), 1)} & m \\
Relieve total & {_n(summary.get('relieve_cuenca_m'), 1)} & m \\
Longitud del cauce principal & {_n(summary.get('main_channel_length_km'))} & km \\
Pendiente global del cauce principal & {_n(summary.get('main_channel_slope_percent'), 2)} & \% \\
Tiempo de concentración - Kirpich & {_n(summary.get('tc_kirpich_h'), 3)} & h \\
Tiempo de concentración - Témez & {_n(summary.get('tc_temez_h'), 3)} & h \\
Tiempo de concentración promedio & {_n(summary.get('tc_promedio_h'), 3)} & h \\
\bottomrule\end{{tabular}}\caption{{Parámetros asociados al relieve y al cauce principal.}}\end{{table}}
{profile_figure}

\section{{Subcuencas}}
{sub_table}
{sub_figure}

\section{{Interpretación técnica}}
{_interpretation(summary)}

\section{{Cartografía técnica}}
\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['dem']}}}\caption{{Contexto regional del DEM y cuenca delimitada.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['hillshade']}}}\caption{{Relieve sombreado de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['accumulation']}}}\caption{{Acumulación de flujo dentro de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['watershed']}}}\caption{{Cuenca, red de drenaje y cauce principal.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.94\textwidth]{{{figures['strahler']}}}\caption{{Orden de Strahler de la red.}}\end{{figure}}

\section{{Información hidrometeorológica}}
La precipitación, temperatura, caudal y series de estaciones no se infieren a partir del DEM. HydroBasin reserva esta sección para datos observados o provenientes de servicios hidrometeorológicos que se integren al proyecto, evitando asignar valores sin una fuente verificable.

\section{{Observaciones y limitaciones}}
La densidad de drenaje, el número de corrientes, las subcuencas y el trazado del cauce principal dependen de la resolución del DEM y del área mínima de aporte seleccionada. Para estudios de diseño o amenaza se recomienda validar la red, el cauce principal, las divisorias y los parámetros con cartografía oficial, imágenes, levantamientos o información de campo.
\end{{document}}
"""
    tex_path.write_text(tex, encoding="utf-8")
    return tex_path.name


def _generar_plano_latex(output_dir: Path, summary: dict, figures: dict[str, str]) -> str:
    tex_path = output_dir / "plano_hidrografico.tex"
    generated_at = datetime.now().strftime("%d/%m/%Y")
    profile = figures.get("profile")
    profile_block = rf"\includegraphics[width=\linewidth]{{{profile}}}" if profile else r"\fbox{\parbox[c][4cm][c]{\linewidth}{\centering Perfil longitudinal no disponible}}"
    tex = rf"""\documentclass[10pt,a3paper,landscape]{{article}}
\usepackage[utf8]{{inputenc}}\usepackage[T1]{{fontenc}}\usepackage[spanish]{{babel}}
\usepackage{{graphicx,geometry,array,xcolor}}\geometry{{margin=8mm}}\pagestyle{{empty}}
\definecolor{{hydro}}{{HTML}}{{1F5F66}}
\begin{{document}}\noindent
\begin{{minipage}}[t][0.96\textheight][t]{{0.235\textwidth}}
\fbox{{\parbox[c][2.0cm][c]{{0.94\linewidth}}{{\centering\color{{hydro}}\Large\bfseries HYDROBASIN\\\small Watershed Studio}}}}\\[2mm]
\fbox{{\parbox[c][1.7cm][c]{{0.94\linewidth}}{{\centering\bfseries PLANO HIDROGRÁFICO\\Cuenca y red de drenaje}}}}\\[2mm]
\small
\begin{{tabular}}{{|p{{3.9cm}}|p{{3.8cm}}|}}\hline
\textbf{{Área}} & {_n(summary.get('area_km2'))} km$^2$ \\\hline
\textbf{{Perímetro}} & {_n(summary.get('perimetro_km'))} km \\\hline
\textbf{{Cauce principal}} & {_n(summary.get('main_channel_length_km'))} km \\\hline
\textbf{{Subcuencas}} & {summary.get('subbasin_count', 'N/D')} \\\hline
\textbf{{Strahler máx.}} & {summary.get('strahler_max', 'N/D')} \\\hline
\textbf{{CRS}} & {_latex_escape(summary.get('crs_calculo') or 'N/D')} \\\hline
\textbf{{Fuente DEM}} & {_latex_escape(summary.get('dem_source') or 'N/D')} \\\hline
\textbf{{Fecha}} & {generated_at} \\\hline
\end{{tabular}}\\[3mm]
\textbf{{Perfil de elevación del cauce principal}}\\[1mm]
{profile_block}
\vfill
\footnotesize Plano generado automáticamente. Las divisorias y drenajes son derivados del DEM y deben validarse para usos de diseño o cartografía oficial.
\end{{minipage}}\hfill
\begin{{minipage}}[t][0.96\textheight][c]{{0.75\textwidth}}
\centering\includegraphics[width=\linewidth,height=0.94\textheight,keepaspectratio]{{{figures['plan']}}}
\end{{minipage}}
\end{{document}}
"""
    tex_path.write_text(tex, encoding="utf-8")
    return tex_path.name


def _find_tectonic() -> str | None:
    return shutil.which("tectonic") or shutil.which("tecto")


def _compile_latex(output_dir: Path, tex_name: str) -> dict:
    tectonic = _find_tectonic()
    pdf_path = output_dir / Path(tex_name).with_suffix(".pdf").name
    if not tectonic:
        return {"compiled": False, "pdf": None, "compiler_found": False, "compiler_path": None, "compile_error": "No se encontró Tectonic. Ejecuta pip install -r requirements.txt en el backend."}
    try:
        completed = subprocess.run([tectonic, tex_name, "--keep-logs", "--keep-intermediates"], cwd=output_dir, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        if completed.returncode != 0 or not pdf_path.exists():
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            detail = " | ".join(lines[-16:])[-3200:]
            return {"compiled": False, "pdf": None, "compiler_found": True, "compiler_path": tectonic, "compile_error": detail or f"Tectonic terminó con código {completed.returncode}."}
        return {"compiled": True, "pdf": pdf_path.name, "compiler_found": True, "compiler_path": tectonic, "compile_error": None}
    except subprocess.TimeoutExpired:
        return {"compiled": False, "pdf": None, "compiler_found": True, "compiler_path": tectonic, "compile_error": "La compilación con Tectonic superó 300 segundos."}
    except Exception as exc:
        return {"compiled": False, "pdf": None, "compiler_found": True, "compiler_path": tectonic, "compile_error": str(exc)}


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None, main_channel=None) -> dict:
    """Genera y compila el informe técnico y un plano hidrográfico independiente."""
    tex_name = _generar_fuente_latex(output_dir, summary, figures, subbasins=subbasins)
    plan_tex = _generar_plano_latex(output_dir, summary, figures)
    report_result = _compile_latex(output_dir, tex_name)
    plan_result = _compile_latex(output_dir, plan_tex)
    compiled = bool(report_result["compiled"] and plan_result["compiled"])
    errors = [item for item in [report_result.get("compile_error"), plan_result.get("compile_error")] if item]
    return {
        "tex": tex_name,
        "pdf": report_result["pdf"],
        "plan_tex": plan_tex,
        "plan_pdf": plan_result["pdf"],
        "compiled": compiled,
        "pdf_engine": "tectonic",
        "compiler_found": report_result["compiler_found"],
        "compiler_path": report_result["compiler_path"],
        "compile_error": " | ".join(errors) if errors else None,
    }
