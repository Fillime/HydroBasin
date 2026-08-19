from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


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
    im = ax.imshow(
        np.where(acc > 0, acc, np.nan),
        extent=extent,
        cmap="viridis",
        norm=LogNorm(vmin=1, vmax=max(1, vmax)),
    )
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


def _n(value, digits=2):
    return "N/D" if value is None else f"{value:.{digits}f}"


def _generar_fuente_latex(output_dir: Path, summary: dict, figures: dict[str, str]) -> str:
    tex_path = output_dir / "informe_hydrobasin.tex"
    area = summary.get("area_km2")
    perimeter = summary.get("perimetro_km")
    max_order = summary.get("strahler_max")
    threshold_area = summary.get("minimum_area_km2")
    crs = str(summary.get("crs_calculo") or summary.get("crs_dem") or "N/D")

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{geometry}}
\usepackage{{float}}
\geometry{{margin=2.5cm}}
\title{{Informe de delimitación y análisis de cuenca hidrográfica}}
\author{{HydroBasin}}
\date{{\today}}
\begin{{document}}
\maketitle

\section{{Objetivo}}
Delimitar la cuenca aportante al exutorio seleccionado a partir de un Modelo Digital de Elevación (DEM), calcular la dirección y acumulación de flujo, extraer la red de drenaje y caracterizar su jerarquía mediante el orden de Strahler.

\section{{Metodología}}
El procesamiento comprende acondicionamiento hidrológico del DEM, dirección de flujo D8, acumulación, ajuste del exutorio, delimitación de la cuenca, extracción de drenajes y orden de Strahler.

\section{{Resultados principales}}
\begin{{tabular}}{{lll}}
\toprule
Parámetro & Valor & Unidad \\
\midrule
Área de la cuenca & {_n(area)} & km$^2$ \\
Perímetro & {_n(perimeter)} & km \\
Área mínima de aporte & {_n(threshold_area, 3)} & km$^2$ \\
Orden máximo de Strahler & {max_order if max_order is not None else 'N/D'} & -- \\
Sistema de referencia & \multicolumn{{2}}{{l}}{{{crs}}} \\
\bottomrule
\end{{tabular}}

\section{{Cartografía}}
\includegraphics[width=0.92\textwidth]{{{figures['dem']}}}
\includegraphics[width=0.92\textwidth]{{{figures['hillshade']}}}
\includegraphics[width=0.92\textwidth]{{{figures['accumulation']}}}
\includegraphics[width=0.92\textwidth]{{{figures['watershed']}}}
\includegraphics[width=0.92\textwidth]{{{figures['strahler']}}}

\end{{document}}
"""
    tex_path.write_text(tex, encoding="utf-8")
    return tex_path.name


def _generar_pdf_directo(output_dir: Path, summary: dict, figures: dict[str, str]) -> str:
    pdf_path = output_dir / "informe_hydrobasin.pdf"
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Informe de delimitación y análisis de cuenca hidrográfica",
        author="HydroBasin",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HydroTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=20,
        leading=24,
        spaceAfter=12,
    )
    subtitle_style = ParagraphStyle(
        "HydroSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#52606d"),
        fontSize=9,
        leading=12,
        spaceAfter=22,
    )
    heading = ParagraphStyle(
        "HydroHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=7,
        textColor=colors.HexColor("#1f4f59"),
    )
    body = ParagraphStyle(
        "HydroBody",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=14,
        spaceAfter=8,
    )
    caption = ParagraphStyle(
        "HydroCaption",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#52606d"),
        spaceAfter=12,
    )

    story = [
        Spacer(1, 1.4 * cm),
        Paragraph("HydroBasin", title_style),
        Paragraph("Informe de delimitación y análisis de cuenca hidrográfica", styles["Heading1"]),
        Paragraph("Informe técnico generado automáticamente a partir del modelo digital de elevación y el exutorio seleccionado.", subtitle_style),
        Paragraph("1. Objetivo", heading),
        Paragraph(
            "Delimitar la cuenca aportante al exutorio seleccionado a partir de un Modelo Digital de Elevación (DEM), calcular la dirección y acumulación de flujo, extraer la red de drenaje y caracterizar su jerarquía mediante el orden de Strahler.",
            body,
        ),
        Paragraph("2. Metodología", heading),
        Paragraph(
            "El flujo de procesamiento comprende acondicionamiento hidrológico del DEM, cálculo de dirección de flujo D8, acumulación de flujo, ajuste del exutorio a una celda de alta acumulación, delimitación de la cuenca, extracción de la red de drenaje, orden de Strahler y cálculo de parámetros morfométricos.",
            body,
        ),
        Paragraph("3. Resultados principales", heading),
    ]

    resolution = summary.get("metric_resolution_m")
    resolution_text = "N/D" if not resolution else f"{resolution[0]:.1f} × {resolution[1]:.1f} m"
    results_data = [
        ["Parámetro", "Valor", "Unidad"],
        ["Área de la cuenca", _n(summary.get("area_km2")), "km²"],
        ["Perímetro", _n(summary.get("perimetro_km")), "km"],
        ["Coeficiente de compacidad", _n(summary.get("coeficiente_compacidad"), 3), "—"],
        ["Relación de circularidad", _n(summary.get("relacion_circularidad"), 3), "—"],
        ["Área mínima de aporte", _n(summary.get("minimum_area_km2"), 3), "km²"],
        ["Umbral de drenaje", _n(summary.get("drainage_threshold"), 0), "celdas"],
        ["Orden máximo de Strahler", str(summary.get("strahler_max", "N/D")), "—"],
        ["Resolución métrica aprox.", resolution_text, ""],
        ["CRS de cálculo", str(summary.get("crs_calculo") or "N/D"), ""],
    ]
    table = Table(results_data, colWidths=[7.2 * cm, 6.1 * cm, 2.2 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4f59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dde2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8f9")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Spacer(1, 10), PageBreak(), Paragraph("4. Cartografía del análisis", heading)])

    figure_specs = [
        ("dem", "Modelo digital de elevación."),
        ("hillshade", "Relieve sombreado del terreno."),
        ("accumulation", "Acumulación de flujo en escala logarítmica."),
        ("watershed", "Límite de la cuenca y red de drenaje."),
        ("strahler", "Orden de corrientes de Strahler."),
    ]
    for key, text in figure_specs:
        image_path = output_dir / figures[key]
        if image_path.exists():
            story.append(Image(str(image_path), width=16.5 * cm, height=12.0 * cm, kind="proportional"))
            story.append(Paragraph(text, caption))

    story.extend([
        Paragraph("5. Observación sobre el umbral de drenaje", heading),
        Paragraph(
            "El área mínima de aporte controla la densidad de la red extraída. Valores menores generan una red más detallada, mientras que valores mayores conservan principalmente los cauces de mayor jerarquía. Este parámetro debe seleccionarse de acuerdo con la escala del estudio y la resolución del DEM.",
            body,
        ),
    ])

    doc.build(story)
    return pdf_path.name


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str]) -> dict:
    """Genera PDF directo y conserva una fuente LaTeX opcional para descarga."""
    tex_name = _generar_fuente_latex(output_dir, summary, figures)
    pdf_name = _generar_pdf_directo(output_dir, summary, figures)
    return {
        "pdf": pdf_name,
        "tex": tex_name,
        "pdf_engine": "reportlab",
    }
