from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np


def _n(value, digits=2):
    if value is None:
        return "N/D"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _tc_min(summary: dict, key: str):
    value = summary.get(key)
    return None if value is None else float(value) * 60.0


def _draw_title_block(ax, summary: dict, loc: dict, sheet_num: int, sheet_title: str):
    """Dibuja un rótulo técnico de ingeniería estándar de 5 columnas."""
    ax.set_xlim(0, 400)
    ax.set_ylim(0, 36)
    ax.axis("off")

    # Borde exterior
    ax.add_patch(Rectangle((0, 0), 400, 36, facecolor="#f8fafc", edgecolor="#1e293b", linewidth=1.2))

    # Líneas divisorias horizontales (4 filas de 9mm)
    for y in [9, 18, 27]:
        ax.plot([0, 400], [y, y], color="#1e293b", linewidth=0.8)

    # Divisiones verticales
    # Fila 1 (y=27..36): PROYECTO (ancho 300) | HOJA (ancho 100)
    ax.plot([300, 300], [27, 36], color="#1e293b", linewidth=0.8)

    # Fila 2 (y=18..27): CLIENTE (160) | CALCULÓ (120) | REVISÓ (120)
    ax.plot([160, 160], [18, 27], color="#1e293b", linewidth=0.8)
    ax.plot([280, 280], [18, 27], color="#1e293b", linewidth=0.8)

    # Fila 3 (y=9..18): UBICACIÓN (200) | FECHA (100) | ESCALA (100)
    ax.plot([200, 200], [9, 18], color="#1e293b", linewidth=0.8)
    ax.plot([300, 300], [9, 18], color="#1e293b", linewidth=0.8)

    # Fila 4 (y=0..9): EXUTORIO (200) | COTA (100) | ÁREA (100)
    ax.plot([200, 200], [0, 9], color="#1e293b", linewidth=0.8)
    ax.plot([300, 300], [0, 9], color="#1e293b", linewidth=0.8)

    # Textos de Fila 1
    proj = summary.get("project_name") or "Cuenca Hidrográfica"
    ax.text(3, 31.5, "PROYECTO:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(28, 31.5, str(proj)[:60], fontsize=8.5, fontweight="bold", color="#0f172a")
    ax.text(303, 31.5, "PLANO / HOJA:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(342, 31.5, f"{sheet_title} | HOJA {sheet_num} DE 2", fontsize=7.5, fontweight="bold", color="#0f172a")

    # Textos de Fila 2
    client = summary.get("client") or "Particular"
    calc = summary.get("calculated_by") or "HydroBasin Studio"
    rev = summary.get("reviewed_by") or "Revisión Técnica"
    ax.text(3, 22.5, "CLIENTE:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(22, 22.5, str(client)[:32], fontsize=8, color="#0f172a")
    ax.text(163, 22.5, "CALCULÓ:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(188, 22.5, str(calc)[:24], fontsize=8, color="#0f172a")
    ax.text(283, 22.5, "REVISÓ:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(304, 22.5, str(rev)[:22], fontsize=8, color="#0f172a")

    # Textos de Fila 3
    if loc.get("country_code") == "COL":
        parts = [loc.get("municipality"), loc.get("department"), loc.get("country")]
        admin = ", ".join(v for v in parts if v) or "Colombia"
    else:
        admin = loc.get("country") or "Ubicación no determinada"
    fecha = datetime.now().strftime("%d/%m/%Y")
    ax.text(3, 13.5, "UBICACIÓN:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(28, 13.5, str(admin)[:45], fontsize=8, fontweight="bold", color="#0f172a")
    ax.text(203, 13.5, "FECHA:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(224, 13.5, fecha, fontsize=8, color="#0f172a")
    ax.text(303, 13.5, "ESCALA / CRS:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(338, 13.5, f"Indicada ({summary.get('crs_calculo') or 'EPSG:32618'})", fontsize=7.5, color="#0f172a")

    # Textos de Fila 4
    outlet = summary.get("outlet_original") or {}
    cota_ex = summary.get("main_channel_elevation_outlet_m") or summary.get("elevacion_min_m")
    cota_str = f"{cota_ex:.1f} msnm" if cota_ex is not None else "N/D"
    ax.text(3, 4.5, "EXUTORIO:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(26, 4.5, f"Lat: {_n(outlet.get('y'),5)}°, Lng: {_n(outlet.get('x'),5)}° (WGS84)", fontsize=8, color="#0f172a")
    ax.text(203, 4.5, "COTA:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(220, 4.5, cota_str, fontsize=8, color="#0f172a")
    ax.text(303, 4.5, "ÁREA CUENCA:", fontsize=7, fontweight="bold", color="#64748b")
    ax.text(338, 4.5, f"{_n(summary.get('area_km2'))} km²", fontsize=8.5, fontweight="bold", color="#0f172a")


def generar_plano_pdf(
    output_pdf: Path,
    summary: dict,
    watershed,
    drainage,
    subbasins,
    main_channel,
    loc: dict,
) -> Path:
    """Genera el plano hidrográfico de 2 hojas en formato A3 horizontal (420 x 297 mm) con perfección milimétrica."""
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    metric_crs = summary.get("crs_calculo") or (watershed.crs if watershed is not None else "EPSG:32618")
    basin = watershed.to_crs(metric_crs) if watershed is not None and not watershed.empty else None
    drains = drainage.to_crs(metric_crs) if drainage is not None and not drainage.empty else None
    subs = subbasins.to_crs(metric_crs) if subbasins is not None and not subbasins.empty else None
    channel = main_channel.to_crs(metric_crs) if main_channel is not None and not main_channel.empty else None

    # A3 Landscape dimensions in inches: 16.54 x 11.69 in (420 x 297 mm)
    fig_width, fig_height = 16.54, 11.69

    with PdfPages(output_pdf) as pdf:
        # =========================================================================
        # HOJA 1: PLANO GENERAL DE LA CUENCA Y RED HIDROGRÁFICA
        # =========================================================================
        fig1 = plt.figure(figsize=(fig_width, fig_height), dpi=200)
        fig1.patch.set_facecolor("#ffffff")

        # Título superior
        fig1.text(0.03, 0.958, "PLANO HIDROGRÁFICO -- DELIMITACIÓN GENERAL Y RED DE DRENAJE", fontsize=13, fontweight="bold", color="#0f172a")
        fig1.text(0.03, 0.942, "HydroBasin Studio | Suite de Análisis Hidrológico y Geomorfología", fontsize=8.5, color="#64748b")

        # Eje del Mapa General [left, bottom, width, height]
        ax_map1 = fig1.add_axes([0.03, 0.16, 0.74, 0.76])
        ax_map1.set_facecolor("#f8fafc")

        if basin is not None:
            if subs is not None:
                subs.plot(ax=ax_map1, column="subbasin_id", cmap="Pastel2", alpha=0.75, edgecolor="#94a3b8", linewidth=0.5)
            else:
                basin.plot(ax=ax_map1, facecolor="#e0f2fe", edgecolor="#0284c7", linewidth=1.2)
            basin.boundary.plot(ax=ax_map1, color="#0f172a", linewidth=1.8)

            if drains is not None:
                drains.plot(ax=ax_map1, color="#2563eb", linewidth=0.7, alpha=0.9)
            if channel is not None:
                channel.plot(ax=ax_map1, color="#dc2626", linewidth=2.4)

            west, south, east, north = basin.total_bounds
            dx, dy = east - west, north - south
            pad = 0.04
            ax_map1.set_xlim(west - dx * pad, east + dx * pad)
            ax_map1.set_ylim(south - dy * pad, north + dy * pad)

            # Escala gráfica
            if dx > 0:
                raw_km = max(0.2, dx / 1000.0 * 0.18)
                exponent = 10 ** np.floor(np.log10(raw_km))
                normalized = raw_km / exponent
                nice = 1 if normalized < 1.5 else 2 if normalized < 3.5 else 5 if normalized < 7.5 else 10
                scale_km = nice * exponent
                x0 = west + dx * 0.05
                y0 = south + dy * 0.05
                x1 = x0 + scale_km * 1000.0
                ax_map1.plot([x0, x1], [y0, y0], color="#0f172a", linewidth=4, solid_capstyle="butt")
                ax_map1.plot([x0, x0], [y0 - dy * 0.006, y0 + dy * 0.006], color="#0f172a", linewidth=1)
                ax_map1.plot([x1, x1], [y0 - dy * 0.006, y0 + dy * 0.006], color="#0f172a", linewidth=1)
                ax_map1.text(x0, y0 + dy * 0.012, "0", fontsize=7.5, ha="center", fontweight="bold")
                ax_map1.text(x1, y0 + dy * 0.012, f"{scale_km:g} km", fontsize=7.5, ha="center", fontweight="bold")

        ax_map1.set_aspect("equal", adjustable="box")
        ax_map1.grid(True, color="#cbd5e1", linewidth=0.5, linestyle="--", alpha=0.7)
        ax_map1.tick_params(labelsize=7.5)
        ax_map1.set_xlabel("Coordenada Este (m)", fontsize=8)
        ax_map1.set_ylabel("Coordenada Norte (m)", fontsize=8)

        # Norte
        ax_map1.annotate("N", xy=(0.06, 0.93), xycoords="axes fraction", ha="center", va="center", fontsize=13, fontweight="bold", color="#0f172a")
        ax_map1.annotate("", xy=(0.06, 0.90), xytext=(0.06, 0.81), xycoords="axes fraction", arrowprops=dict(arrowstyle="-|>", lw=1.8, color="#0f172a"))

        # Leyenda
        legend_elements = [
            Patch(facecolor="#e0f2fe", edgecolor="#0f172a", label="Divisoria de Cuenca"),
            Line2D([0], [0], color="#2563eb", lw=1.2, label="Red de Drenaje"),
            Line2D([0], [0], color="#dc2626", lw=2.4, label="Cauce Principal"),
        ]
        ax_map1.legend(handles=legend_elements, loc="lower right", frameon=True, framealpha=0.92, fontsize=7.5, title="CONVENCIONES", title_fontsize=8)

        # Eje de Cuadro Técnico Lateral
        ax_table1 = fig1.add_axes([0.79, 0.16, 0.18, 0.76])
        ax_table1.axis("off")
        ax_table1.add_patch(Rectangle((0, 0), 1, 1, facecolor="#f8fafc", edgecolor="#cbd5e1", linewidth=1, transform=ax_table1.transAxes))

        tc_k = _tc_min(summary, "tc_kirpich_h")
        tc_t = _tc_min(summary, "tc_temez_h")
        desnivel = (summary.get("main_channel_elevation_source_m") or 0) - (summary.get("main_channel_elevation_outlet_m") or 0)

        tech_text = [
            ("Área Cuenca", f"{_n(summary.get('area_km2'))} km²"),
            ("Perímetro", f"{_n(summary.get('perimetro_km'))} km"),
            ("Longitud Axial", f"{_n(summary.get('longitud_axial_km'))} km"),
            ("Factor Forma (Kf)", f"{_n(summary.get('factor_forma'), 3)}"),
            ("Compacidad (Kc)", f"{_n(summary.get('coeficiente_compacidad'), 3)}"),
            ("Circularidad (Rc)", f"{_n(summary.get('relacion_circularidad'), 3)}"),
            ("Dens. Drenaje", f"{_n(summary.get('densidad_drenaje_km_km2'), 3)} km/km²"),
            ("Orden Strahler", f"{summary.get('strahler_max', 'N/D')}"),
            ("Subcuencas", f"{summary.get('subbasin_count', 'N/D')}"),
            ("Long. Cauce", f"{_n(summary.get('main_channel_length_km'))} km"),
            ("Desnivel Total", f"{_n(desnivel)} m"),
            ("Pendiente Media", f"{_n(summary.get('main_channel_slope_percent'), 2)}%"),
            ("Tc Kirpich", f"{_n(tc_k)} min"),
            ("Tc Témez", f"{_n(tc_t)} min"),
            ("Cota Mínima", f"{_n(summary.get('elevacion_min_m'))} m"),
            ("Cota Máxima", f"{_n(summary.get('elevacion_max_m'))} m"),
        ]

        ax_table1.text(0.08, 0.94, "CUADRO TÉCNICO", fontsize=9, fontweight="bold", color="#0f172a", transform=ax_table1.transAxes)
        ax_table1.plot([0.08, 0.92], [0.92, 0.92], color="#cbd5e1", lw=1, transform=ax_table1.transAxes)

        y_pos = 0.87
        for label, val in tech_text:
            ax_table1.text(0.08, y_pos, label, fontsize=7.5, color="#64748b", transform=ax_table1.transAxes)
            ax_table1.text(0.92, y_pos, val, fontsize=7.5, fontweight="bold", color="#0f172a", ha="right", transform=ax_table1.transAxes)
            y_pos -= 0.052

        # Eje del Rótulo Inferior
        ax_title1 = fig1.add_axes([0.03, 0.025, 0.94, 0.115])
        _draw_title_block(ax_title1, summary, loc, 1, "Delimitación general y red de drenaje")

        pdf.savefig(fig1)
        plt.close(fig1)

        # =========================================================================
        # HOJA 2: SUBCUENCAS Y PERFIL LONGITUDINAL DEL CAUCE
        # =========================================================================
        fig2 = plt.figure(figsize=(fig_width, fig_height), dpi=200)
        fig2.patch.set_facecolor("#ffffff")

        # Título superior
        fig2.text(0.03, 0.958, "PLANO HIDROGRÁFICO -- SUBCUENCAS Y PERFIL LONGITUDINAL DEL CAUCE", fontsize=13, fontweight="bold", color="#0f172a")
        fig2.text(0.03, 0.942, "HydroBasin Studio | Suite de Análisis Hidrológico y Geomorfología", fontsize=8.5, color="#64748b")

        # Eje del Mapa de Subcuencas (Izquierda)
        ax_map2 = fig2.add_axes([0.03, 0.16, 0.48, 0.76])
        ax_map2.set_facecolor("#f8fafc")

        if basin is not None:
            if subs is not None:
                subs.plot(ax=ax_map2, column="subbasin_id", cmap="tab20", alpha=0.6, edgecolor="#64748b", linewidth=0.6)
            basin.boundary.plot(ax=ax_map2, color="#0f172a", linewidth=1.8)
            if drains is not None:
                drains.plot(ax=ax_map2, color="#2563eb", linewidth=0.6, alpha=0.85)
            if channel is not None:
                channel.plot(ax=ax_map2, color="#dc2626", linewidth=2.2)

            ax_map2.set_xlim(west - dx * pad, east + dx * pad)
            ax_map2.set_ylim(south - dy * pad, north + dy * pad)

        ax_map2.set_aspect("equal", adjustable="box")
        ax_map2.grid(True, color="#cbd5e1", linewidth=0.5, linestyle="--", alpha=0.7)
        ax_map2.tick_params(labelsize=7.5)
        ax_map2.set_xlabel("Coordenada Este (m)", fontsize=8)
        ax_map2.set_ylabel("Coordenada Norte (m)", fontsize=8)
        ax_map2.set_title("Subdivisión en Subcuencas Hidrológicas", fontsize=9.5, fontweight="bold")

        # Eje de Características del Cauce y Caudales de Diseño (Derecha Arriba)
        ax_chan_table = fig2.add_axes([0.54, 0.58, 0.43, 0.34])
        ax_chan_table.axis("off")
        ax_chan_table.add_patch(Rectangle((0, 0), 1, 1, facecolor="#f8fafc", edgecolor="#cbd5e1", linewidth=1, transform=ax_chan_table.transAxes))

        # División interna: mitad izquierda características, mitad derecha caudales Tr
        ax_chan_table.plot([0.52, 0.52], [0.05, 0.95], color="#cbd5e1", lw=0.8, transform=ax_chan_table.transAxes)

        tc_p_min = _tc_min(summary, "tc_promedio_h")

        chan_text = [
            ("Longitud Cauce (L)", f"{_n(summary.get('main_channel_length_km'))} km"),
            ("Cota Cabecera", f"{_n(summary.get('main_channel_elevation_source_m'))} m"),
            ("Cota Exutorio", f"{_n(summary.get('main_channel_elevation_outlet_m'))} m"),
            ("Desnivel (ΔH)", f"{_n(desnivel)} m"),
            ("Pendiente (S)", f"{_n(summary.get('main_channel_slope_percent'), 2)}%"),
            ("Tc Kirpich", f"{_n(tc_k)} min"),
            ("Tc Témez", f"{_n(tc_t)} min"),
            ("Tc Promedio", f"{_n(tc_p_min)} min"),
        ]

        ax_chan_table.text(0.04, 0.91, "PARÁMETROS DEL CAUCE", fontsize=8, fontweight="bold", color="#0f172a", transform=ax_chan_table.transAxes)
        ax_chan_table.plot([0.04, 0.48], [0.86, 0.86], color="#cbd5e1", lw=1, transform=ax_chan_table.transAxes)

        y_pos = 0.77
        for label, val in chan_text:
            ax_chan_table.text(0.04, y_pos, label, fontsize=7.2, color="#64748b", transform=ax_chan_table.transAxes)
            ax_chan_table.text(0.48, y_pos, val, fontsize=7.2, fontweight="bold", color="#0f172a", ha="right", transform=ax_chan_table.transAxes)
            y_pos -= 0.095

        # Caudales de Diseño Tr
        ax_chan_table.text(0.56, 0.91, "CAUDALES MÁXIMOS (Qp)", fontsize=8, fontweight="bold", color="#0f172a", transform=ax_chan_table.transAxes)
        ax_chan_table.plot([0.56, 0.96], [0.86, 0.86], color="#cbd5e1", lw=1, transform=ax_chan_table.transAxes)

        peak_flows = summary.get("peak_discharges") or []
        y_q = 0.77
        if peak_flows:
            for q in peak_flows:
                tr_lbl = f"Tr = {q['tr_anos']} años"
                q_val = f"{_n(q['caudal_diseno_m3_s'])} m³/s"
                ax_chan_table.text(0.56, y_q, tr_lbl, fontsize=7.2, color="#64748b", transform=ax_chan_table.transAxes)
                ax_chan_table.text(0.96, y_q, q_val, fontsize=7.2, fontweight="bold", color="#dc2626", ha="right", transform=ax_chan_table.transAxes)
                y_q -= 0.095
        else:
            ax_chan_table.text(0.56, 0.70, "CN = " + str(_n(summary.get("cn_weighted"), 1)), fontsize=7.5, color="#64748b", transform=ax_chan_table.transAxes)

        # Eje del Perfil Longitudinal (Derecha Abajo)
        ax_prof = fig2.add_axes([0.54, 0.16, 0.43, 0.38])
        distances = summary.get("profile_distance_km") or []
        elevations = summary.get("profile_elevation_m") or []

        if len(distances) >= 2 and len(distances) == len(elevations):
            ax_prof.plot(distances, elevations, color="#0284c7", linewidth=2.2, label="Perfil Altimétrico")
            min_e = min(elevations)
            ax_prof.fill_between(distances, elevations, min_e, color="#0284c7", alpha=0.15)

            ax_prof.scatter([distances[0]], [elevations[0]], color="#dc2626", s=45, zorder=5)
            ax_prof.annotate(f"Exutorio: {elevations[0]:.1f} m", (distances[0], elevations[0]), xytext=(8, 8), textcoords="offset points", fontsize=7.5, fontweight="bold", bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#dc2626", lw=0.8))

            ax_prof.scatter([distances[-1]], [elevations[-1]], color="#2563eb", s=45, zorder=5)
            ax_prof.annotate(f"Cabecera: {elevations[-1]:.1f} m", (distances[-1], elevations[-1]), xytext=(-65, 8), textcoords="offset points", fontsize=7.5, fontweight="bold", bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#2563eb", lw=0.8))

            ax_prof.set_xlabel("Distancia acumulada desde el exutorio (km)", fontsize=8)
            ax_prof.set_ylabel("Elevación (msnm)", fontsize=8)
            ax_prof.grid(True, color="#cbd5e1", linestyle="--", linewidth=0.5, alpha=0.7)
            ax_prof.tick_params(labelsize=7.5)
            ax_prof.set_title("Perfil Longitudinal del Cauce Principal", fontsize=9, fontweight="bold")

        # Eje del Rótulo Inferior
        ax_title2 = fig2.add_axes([0.03, 0.025, 0.94, 0.115])
        _draw_title_block(ax_title2, summary, loc, 2, "Subcuencas y perfil longitudinal del cauce")

        pdf.savefig(fig2)
        plt.close(fig2)

    return output_pdf
