from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#1f5f66")
TEXT = colors.HexColor("#202529")
MUTED = colors.HexColor("#68727a")
RULE = colors.HexColor("#d8dde0")
SOFT = colors.HexColor("#f5f7f8")


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


def _generar_fuente_latex(output_dir: Path, summary: dict, figures: dict[str, str]) -> str:
    tex_path = output_dir / "informe_hydrobasin.tex"
    subfigure = ""
    if figures.get("subbasins"):
        subfigure = rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{figures['subbasins']}}}
\caption{{Subcuencas hidrológicas dentro de la cuenca principal.}}
\end{{figure}}
"""

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{geometry}}
\usepackage{{float}}
\usepackage{{microtype}}
\usepackage{{fancyhdr}}
\geometry{{margin=2.5cm}}
\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{HydroBasin}}
\rhead{{Análisis de cuenca}}
\cfoot{{\thepage}}
\title{{\textbf{{Informe de delimitación y análisis de cuenca hidrográfica}}}}
\author{{HydroBasin Watershed Studio}}
\date{{\today}}
\begin{{document}}
\maketitle
\tableofcontents
\newpage

\section{{Objeto y alcance}}
El presente informe documenta la delimitación automática de la cuenca aportante al exutorio seleccionado y la caracterización de su estructura de drenaje a partir de un Modelo Digital de Elevación (DEM).

\section{{Metodología}}
El procesamiento comprende acondicionamiento hidrológico del DEM, dirección de flujo D8, acumulación, ajuste del exutorio, delimitación de la cuenca principal, extracción de la red, jerarquización de Strahler y subdivisión hidrológica interna.

\section{{Resultados}}
\begin{{table}}[H]
\centering
\begin{{tabular}}{{lll}}
\toprule
Parámetro & Valor & Unidad \\
\midrule
Área de la cuenca & {_n(summary.get('area_km2'))} & km$^2$ \\
Perímetro & {_n(summary.get('perimetro_km'))} & km \\
Coeficiente de compacidad & {_n(summary.get('coeficiente_compacidad'), 3)} & -- \\
Relación de circularidad & {_n(summary.get('relacion_circularidad'), 3)} & -- \\
Área mínima de aporte & {_n(summary.get('minimum_area_km2'), 3)} & km$^2$ \\
Orden máximo de Strahler & {summary.get('strahler_max', 'N/D')} & -- \\
Número de subcuencas & {summary.get('subbasin_count', 'N/D')} & -- \\
\bottomrule
\end{{tabular}}
\caption{{Síntesis de parámetros hidrológicos y morfométricos.}}
\end{{table}}

\section{{Cartografía técnica}}
\begin{{figure}}[H]\centering\includegraphics[width=0.92\textwidth]{{{figures['dem']}}}\caption{{Contexto regional del DEM y límite de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.92\textwidth]{{{figures['hillshade']}}}\caption{{Relieve sombreado de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.92\textwidth]{{{figures['accumulation']}}}\caption{{Acumulación de flujo dentro de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.92\textwidth]{{{figures['watershed']}}}\caption{{Cuenca principal y red de drenaje.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.92\textwidth]{{{figures['strahler']}}}\caption{{Jerarquía de la red según Strahler.}}\end{{figure}}
{subfigure}

\section{{Criterio de extracción de drenajes}}
El área mínima de aporte controla la densidad de la red. Valores menores representan cauces potenciales de menor jerarquía; valores mayores conservan principalmente los drenajes estructurales de la cuenca.
\end{{document}}
"""
    tex_path.write_text(tex, encoding="utf-8")
    return tex_path.name


def _page_header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, height - 1.25 * cm, width - doc.rightMargin, height - 1.25 * cm)
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, height - 0.92 * cm, "HydroBasin · Informe de análisis hidrográfico")
    canvas.drawRightString(width - doc.rightMargin, 0.8 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _cover_footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(1.2)
    canvas.line(doc.leftMargin, 1.0 * cm, width - doc.rightMargin, 1.0 * cm)
    canvas.setFont("Times-Italic", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 0.65 * cm, "Generado automáticamente por HydroBasin Watershed Studio")
    canvas.restoreState()


def _generar_pdf_directo(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None) -> str:
    pdf_path = output_dir / "informe_hydrobasin.pdf"
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=2.25 * cm,
        leftMargin=2.25 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.6 * cm,
        title="Informe de delimitación y análisis de cuenca hidrográfica",
        author="HydroBasin",
    )

    styles = getSampleStyleSheet()
    cover_brand = ParagraphStyle("CoverBrand", fontName="Times-Bold", fontSize=13, leading=16, textColor=ACCENT, spaceAfter=8)
    cover_title = ParagraphStyle("CoverTitle", fontName="Times-Bold", fontSize=26, leading=31, textColor=TEXT, spaceAfter=14)
    cover_subtitle = ParagraphStyle("CoverSubtitle", fontName="Times-Roman", fontSize=11, leading=16, textColor=MUTED, spaceAfter=22)
    heading = ParagraphStyle("Heading", fontName="Times-Bold", fontSize=15, leading=18, textColor=TEXT, spaceBefore=10, spaceAfter=8)
    subheading = ParagraphStyle("SubHeading", fontName="Times-Bold", fontSize=11.5, leading=14, textColor=ACCENT, spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("Body", fontName="Times-Roman", fontSize=10.2, leading=15, textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=8)
    caption = ParagraphStyle("Caption", fontName="Times-Italic", fontSize=8.8, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceAfter=9)
    small = ParagraphStyle("Small", fontName="Times-Roman", fontSize=8.5, leading=11, textColor=MUTED)
    toc = ParagraphStyle("TOC", fontName="Times-Roman", fontSize=10.5, leading=18, textColor=TEXT)

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    resolution = summary.get("metric_resolution_m")
    resolution_text = "N/D" if not resolution else f"{resolution[0]:.1f} × {resolution[1]:.1f} m"

    meta_data = [
        ["Área delimitada", f"{_n(summary.get('area_km2'))} km²"],
        ["Exutorio", f"{summary.get('outlet_original', {}).get('y', 'N/D')}, {summary.get('outlet_original', {}).get('x', 'N/D')}"],
        ["CRS de cálculo", str(summary.get("crs_calculo") or summary.get("crs_dem") or "N/D")],
        ["Resolución aproximada", resolution_text],
        ["Fecha de procesamiento", now],
    ]
    meta_table = Table(meta_data, colWidths=[5.0 * cm, 9.2 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story = [
        Spacer(1, 2.1 * cm),
        Paragraph("HYDROBASIN / WATERSHED STUDIO", cover_brand),
        Paragraph("Informe de delimitación y análisis de cuenca hidrográfica", cover_title),
        Paragraph(
            "Procesamiento reproducible del modelo digital de elevación, delimitación de la cuenca aportante, estructura de drenaje, jerarquía de corrientes y subdivisión hidrológica interna.",
            cover_subtitle,
        ),
        Spacer(1, 0.7 * cm),
        meta_table,
        Spacer(1, 1.3 * cm),
        Paragraph("Documento técnico generado automáticamente. Los resultados dependen de la resolución, calidad y acondicionamiento del DEM, así como del criterio de área mínima de aporte adoptado.", small),
        PageBreak(),
        Paragraph("Contenido", heading),
        Paragraph("1. Objeto y alcance", toc),
        Paragraph("2. Metodología de procesamiento", toc),
        Paragraph("3. Resultados hidrológicos y morfométricos", toc),
        Paragraph("4. Subcuencas", toc),
        Paragraph("5. Cartografía técnica", toc),
        Paragraph("6. Criterio de extracción de drenajes", toc),
        PageBreak(),
        Paragraph("1. Objeto y alcance", heading),
        Paragraph(
            "El presente informe documenta la delimitación de la cuenca hidrográfica que aporta al exutorio seleccionado. El análisis se obtiene directamente del DEM y comprende la estructura de drenaje superficial derivada, la jerarquización de corrientes y la subdivisión de la cuenca en unidades hidrológicas internas.",
            body,
        ),
        Paragraph("2. Metodología de procesamiento", heading),
        Paragraph("2.1 Acondicionamiento hidrológico", subheading),
        Paragraph("Se corrigen pits, depresiones y zonas planas para obtener una superficie hidrológicamente conectada y apta para el cálculo de flujo.", body),
        Paragraph("2.2 Dirección y acumulación", subheading),
        Paragraph("La dirección de flujo se calcula mediante el esquema D8. La acumulación representa el número de celdas que aportan aguas arriba a cada celda del modelo.", body),
        Paragraph("2.3 Exutorio, cuenca y red", subheading),
        Paragraph("El exutorio indicado por el usuario se ajusta a una celda de alta acumulación. A partir de ese punto se delimita la cuenca principal y se extrae la red de drenaje según el área mínima de aporte seleccionada.", body),
        Paragraph("2.4 Jerarquía y subcuencas", subheading),
        Paragraph("La red se jerarquiza mediante el orden de Strahler. Las subcuencas se estructuran dentro de la cuenca principal utilizando confluencias y salidas de la red D8 como puntos de control, generando unidades no solapadas asociadas a la organización del drenaje.", body),
        Paragraph("3. Resultados hidrológicos y morfométricos", heading),
    ]

    results_data = [
        ["Parámetro", "Resultado", "Unidad"],
        ["Área de la cuenca", _n(summary.get("area_km2")), "km²"],
        ["Perímetro", _n(summary.get("perimetro_km")), "km"],
        ["Coeficiente de compacidad", _n(summary.get("coeficiente_compacidad"), 3), "—"],
        ["Relación de circularidad", _n(summary.get("relacion_circularidad"), 3), "—"],
        ["Área mínima de aporte", _n(summary.get("minimum_area_km2"), 3), "km²"],
        ["Umbral de drenaje", _n(summary.get("drainage_threshold"), 0), "celdas"],
        ["Orden máximo de Strahler", str(summary.get("strahler_max", "N/D")), "—"],
        ["Número de subcuencas", str(summary.get("subbasin_count", "N/D")), "—"],
        ["Resolución métrica aprox.", resolution_text, ""],
        ["CRS de cálculo", str(summary.get("crs_calculo") or "N/D"), ""],
    ]
    table = Table(results_data, colWidths=[7.2 * cm, 5.6 * cm, 2.2 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 10), Paragraph("4. Subcuencas", heading)])

    if subbasins is not None and not subbasins.empty:
        story.append(Paragraph(
            f"Se identificaron <b>{len(subbasins)}</b> unidades hidrológicas internas. Estas subcuencas representan una partición de la cuenca principal controlada por la red de drenaje derivada del DEM y permiten analizar aportes, organización espacial y jerarquía del sistema con mayor detalle.",
            body,
        ))
        if "area_km2" in subbasins.columns:
            largest = subbasins.sort_values("area_km2", ascending=False).head(10)
            rows = [["ID", "Área (km²)"]]
            rows += [[str(int(r.subbasin_id)), f"{float(r.area_km2):.2f}"] for _, r in largest.iterrows()]
            subtable = Table(rows, colWidths=[4.0 * cm, 5.0 * cm], repeatRows=1)
            subtable.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eeee")),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([Paragraph("Subcuencas de mayor área", subheading), subtable])
    else:
        story.append(Paragraph("No fue posible construir una subdivisión interna con el umbral de drenaje utilizado.", body))

    story.extend([PageBreak(), Paragraph("5. Cartografía técnica", heading)])
    figure_specs = [
        ("dem", "Figura 1. Contexto regional del DEM y ubicación de la cuenca delimitada."),
        ("hillshade", "Figura 2. Relieve sombreado encuadrado a la cuenca principal."),
        ("accumulation", "Figura 3. Acumulación de flujo dentro de la cuenca, representada en escala logarítmica."),
        ("watershed", "Figura 4. Límite de la cuenca principal y red de drenaje derivada."),
        ("strahler", "Figura 5. Jerarquía de corrientes según el orden de Strahler."),
        ("subbasins", "Figura 6. Subcuencas hidrológicas internas y su relación con la red de drenaje."),
    ]
    for key, text in figure_specs:
        if not figures.get(key):
            continue
        image_path = output_dir / figures[key]
        if image_path.exists():
            story.append(KeepTogether([
                Image(str(image_path), width=15.7 * cm, height=10.8 * cm, kind="proportional"),
                Paragraph(text, caption),
            ]))

    story.extend([
        Paragraph("6. Criterio de extracción de drenajes", heading),
        Paragraph(
            "El área mínima de aporte es un parámetro de escala. Un valor pequeño produce una red densa que puede incluir vaguadas y cauces potenciales no representados en la cartografía base; al aumentar el valor se conservan progresivamente los drenajes de mayor jerarquía. Por tanto, la selección debe responder al objetivo del estudio, la resolución del DEM y la escala de representación requerida.",
            body,
        ),
    ])

    doc.build(story, onFirstPage=_cover_footer, onLaterPages=_page_header_footer)
    return pdf_path.name


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None) -> dict:
    """Genera un PDF técnico directo y conserva una fuente LaTeX opcional."""
    tex_name = _generar_fuente_latex(output_dir, summary, figures)
    pdf_name = _generar_pdf_directo(output_dir, summary, figures, subbasins=subbasins)
    return {"pdf": pdf_name, "tex": tex_name, "pdf_engine": "reportlab"}
