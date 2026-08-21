from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor


def _set_cell_bg(cell, hex_color: str):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def _format_table(table, col_widths=None):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(table.rows):
        is_header = r_idx == 0
        for c_idx, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_margins(cell, top=110, bottom=110, left=160, right=160)
            if is_header:
                _set_cell_bg(cell, "1F9D8F")
                for p in cell.paragraphs:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    for run in p.runs:
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
                        run.font.size = Pt(9.5)
            else:
                if r_idx % 2 == 1:
                    _set_cell_bg(cell, "F8FAFC")
                else:
                    _set_cell_bg(cell, "FFFFFF")
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(9)
                        run.font.color.rgb = RGBColor(15, 23, 42)
            if col_widths and c_idx < len(col_widths):
                cell.width = Inches(col_widths[c_idx])


def generar_informe_docx(
    output_docx: Path,
    summary: dict,
    figures: dict[str, str],
    subbasins=None,
    loc: dict | None = None,
) -> Path:
    """Genera un informe técnico formal en formato Microsoft Word (.docx)."""
    loc = loc or {}
    output_docx = Path(output_docx).resolve()
    output_docx.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # Configuración de márgenes (2.2 cm = 0.86 in)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.86)
        section.bottom_margin = Inches(0.86)
        section.left_margin = Inches(0.86)
        section.right_margin = Inches(0.86)

    site = summary.get("project_name") or "Cuenca Hidrográfica"
    client = summary.get("client") or "Particular"
    calc = summary.get("calculated_by") or "HydroBasin Studio"
    rev = summary.get("reviewed_by") or "Revisión Técnica"
    admin_label = summary.get("location_label") or "Colombia"

    # ============================== PORTADA ==============================
    p_top = doc.add_paragraph()
    r_top = p_top.add_run("HYDROBASIN STUDIO — INGENIERÍA HIDROLÓGICA")
    r_top.font.bold = True
    r_top.font.size = Pt(11)
    r_top.font.color.rgb = RGBColor(31, 157, 143)

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    r_main = title_p.add_run("ESTUDIO HIDROLÓGICO Y MORFOMÉTRICO DE CUENCA\n")
    r_main.font.bold = True
    r_main.font.size = Pt(22)
    r_main.font.color.rgb = RGBColor(15, 23, 42)

    r_sub = title_p.add_run(f"{site}\n")
    r_sub.font.bold = True
    r_sub.font.size = Pt(15)
    r_sub.font.color.rgb = RGBColor(31, 157, 143)

    r_loc = title_p.add_run(f"{admin_label}\n\n")
    r_loc.font.size = Pt(11)
    r_loc.font.color.rgb = RGBColor(100, 116, 139)

    # Cuadro de Autoría y Revisión
    t_meta = doc.add_table(rows=3, cols=3)
    t_meta.rows[0].cells[0].paragraphs[0].add_run("ELABORÓ:")
    t_meta.rows[0].cells[1].paragraphs[0].add_run("REVISÓ:")
    t_meta.rows[0].cells[2].paragraphs[0].add_run("FECHA:")
    t_meta.rows[1].cells[0].paragraphs[0].add_run(calc)
    t_meta.rows[1].cells[1].paragraphs[0].add_run(rev)
    t_meta.rows[1].cells[2].paragraphs[0].add_run(datetime.now().strftime("%d/%m/%Y"))
    t_meta.rows[2].cells[0].paragraphs[0].add_run(f"CLIENTE: {client}")
    t_meta.rows[2].cells[1].paragraphs[0].add_run("ESTADO: Aprobado")
    t_meta.rows[2].cells[2].paragraphs[0].add_run("VERSIÓN: 1.0")
    _format_table(t_meta, [2.3, 2.3, 2.0])

    doc.add_page_break()

    # ============================== CAPÍTULOS ==============================
    def add_h1(text):
        h = doc.add_heading(text, level=1)
        for r in h.runs:
            r.font.color.rgb = RGBColor(23, 107, 115)
            r.font.bold = True
        return h

    def add_h2(text):
        h = doc.add_heading(text, level=2)
        for r in h.runs:
            r.font.color.rgb = RGBColor(31, 157, 143)
            r.font.bold = True
        return h

    def add_fig(key, caption):
        fig_rel = figures.get(key)
        if fig_rel:
            full_p = output_docx.parent / fig_rel
            if full_p.exists():
                try:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.add_run().add_picture(str(full_p), width=Inches(5.8))
                    cap = doc.add_paragraph()
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    r_c = cap.add_run(f"Figura: {caption}")
                    r_c.font.italic = True
                    r_c.font.size = Pt(8.5)
                    r_c.font.color.rgb = RGBColor(100, 116, 139)
                except Exception:
                    pass

    # 1. Introducción
    add_h1("1. Introducción")
    doc.add_paragraph(
        f"El presente documento corresponde al informe técnico del estudio hidrológico y geomorfológico desarrollado para el proyecto {site}, localizado en {admin_label}. "
        "En este informe se presentan los criterios técnicos, la metodología y los resultados obtenidos en la delimitación de la divisoria de aguas, caracterización física de la cuenca, "
        "consulta de estaciones meteorológicas del IDEAM, análisis pluviométrico con polígonos de Thiessen, familias de curvas IDF, determinación del Número de Curva SCS (CN) "
        "y modelación de caudales máximos de escorrentía para diferentes periodos de retorno."
    )

    # 2. Objetivo y Alcance
    add_h1("2. Objetivo y Alcance")
    add_h2("Objetivo")
    doc.add_paragraph(
        f"Delimitar y caracterizar geomorfológica e hidrológicamente la cuenca aportante al punto de interés del proyecto {site}, determinando sus parámetros morfométricos, "
        "red de drenaje, tiempos de concentración y caudales de diseño hacia el exutorio."
    )
    add_h2("Alcance")
    doc.add_paragraph(
        "El alcance comprende la delimitación topográfica de la cuenca sobre modelo digital de elevación, el análisis morfométrico dimensional, la partición en subcuencas tributarias, "
        "la consulta de la red de estaciones pluviométricas del IDEAM, el cálculo de polígonos de Thiessen, la formulación de curvas IDF regionales, la estimación del Número de Curva (SCS-CN) "
        "y la modelación de hidrogramas y caudales pico para periodos de retorno de 2.33, 5, 10, 25, 50 y 100 años."
    )

    # 3. Localización
    add_h1("3. Localización y Ubicación General")
    outlet = summary.get("outlet_original") or {}
    cota_ex = summary.get("main_channel_elevation_outlet_m") or summary.get("elevacion_min_m")
    cota_str = f"{cota_ex:.1f} msnm" if cota_ex is not None else "N/D"
    doc.add_paragraph(
        f"El proyecto se localiza en la jurisdicción de {admin_label}. El punto de cierre o exutorio fijado para la cuenca se ubica en las coordenadas geográficas "
        f"{outlet.get('y', 0):.6f}° Latitud Norte, {outlet.get('x', 0):.6f}° Longitud Oeste (WGS84), a una cota de {cota_str}."
    )
    add_fig("location_satellite", "Localización regional del área de estudio sobre imagen satelital Esri World Imagery.")

    # 4. Topografía
    add_h1("4. Información Topográfica y Acondicionamiento del Terreno")
    doc.add_paragraph(
        f"La caracterización geomorfológica se fundamentó en el Modelo Digital de Elevación (DEM) {summary.get('dem_source') or 'Copernicus GLO-30'}, con resolución métrica. "
        "La superficie fue sometida a corrección hidrológica mediante el relleno de depresiones cerradas (sinks/pits), garantizando flujo continuo bajo el esquema determinístico D8."
    )

    # 5. Morfometría
    add_h1("5. Clasificación y Parámetros Morfométricos de la Cuenca")
    t_morf = doc.add_table(rows=1, cols=2)
    t_morf.rows[0].cells[0].paragraphs[0].add_run("Parámetro Morfométrico")
    t_morf.rows[0].cells[1].paragraphs[0].add_run("Valor Obtenido")

    morf_data = [
        ("Área de la Cuenca (A)", f"{summary.get('area_km2', 0):.2f} km²"),
        ("Perímetro de la Cuenca (P)", f"{summary.get('perimetro_km', 0):.2f} km"),
        ("Longitud Axial (La)", f"{summary.get('longitud_axial_km', 0):.2f} km"),
        ("Factor de Forma de Horton (Kf)", f"{summary.get('factor_forma', 0):.3f}"),
        ("Coeficiente de Compacidad de Gravelius (Kc)", f"{summary.get('coeficiente_compacidad', 0):.3f}"),
        ("Relación de Circularidad de Miller (Rc)", f"{summary.get('relacion_circularidad', 0):.3f}"),
        ("Densidad de Drenaje (Dd)", f"{summary.get('densidad_drenaje_km_km2', 0):.3f} km/km²"),
        ("Orden Máximo de Corrientes (Strahler)", str(summary.get("strahler_max", "N/D"))),
        ("Número de Subcuencas", str(summary.get("subbasin_count", "N/D"))),
        ("Elevación Mínima (Exutorio)", f"{summary.get('elevacion_min_m', 0):.2f} msnm"),
        ("Elevación Máxima (Cabecera)", f"{summary.get('elevacion_max_m', 0):.2f} msnm"),
        ("Elevación Media", f"{summary.get('elevacion_media_m', 0):.2f} msnm"),
        ("Relieve Total (HT)", f"{summary.get('relieve_cuenca_m', 0):.2f} m"),
    ]
    for label, val in morf_data:
        r = t_morf.add_row()
        r.cells[0].paragraphs[0].add_run(label)
        r.cells[1].paragraphs[0].add_run(val)
    _format_table(t_morf, [4.2, 2.4])

    # 6. Tiempo de Concentración
    add_h1("6. Estimación del Tiempo de Concentración (Tc)")
    tc_k = (summary.get("tc_kirpich_h") or 1.0)
    tc_t = (summary.get("tc_temez_h") or 1.0)
    tc_p = (summary.get("tc_promedio_h") or 1.0)

    t_tc = doc.add_table(rows=1, cols=3)
    t_tc.rows[0].cells[0].paragraphs[0].add_run("Método")
    t_tc.rows[0].cells[1].paragraphs[0].add_run("Tc (Horas)")
    t_tc.rows[0].cells[2].paragraphs[0].add_run("Tc (Minutos)")
    tc_items = [
        ("Kirpich", f"{tc_k:.2f} h", f"{tc_k * 60:.1f} min"),
        ("Témez", f"{tc_t:.2f} h", f"{tc_t * 60:.1f} min"),
        ("Promedio Adoptado", f"{tc_p:.2f} h", f"{tc_p * 60:.1f} min"),
    ]
    for m, h, mnt in tc_items:
        r = t_tc.add_row()
        r.cells[0].paragraphs[0].add_run(m)
        r.cells[1].paragraphs[0].add_run(h)
        r.cells[2].paragraphs[0].add_run(mnt)
    _format_table(t_tc, [2.8, 1.9, 1.9])

    # 7. Estaciones IDEAM
    add_h1("7. Información Meteorológica y Estaciones IDEAM")
    stations = summary.get("ideam_stations") or []
    if stations:
        t_st = doc.add_table(rows=1, cols=6)
        t_st.rows[0].cells[0].paragraphs[0].add_run("Código")
        t_st.rows[0].cells[1].paragraphs[0].add_run("Nombre")
        t_st.rows[0].cells[2].paragraphs[0].add_run("Categoría")
        t_st.rows[0].cells[3].paragraphs[0].add_run("Altitud")
        t_st.rows[0].cells[4].paragraphs[0].add_run("Municipio")
        t_st.rows[0].cells[5].paragraphs[0].add_run("Distancia")
        for s in stations[:8]:
            r = t_st.add_row()
            r.cells[0].paragraphs[0].add_run(str(s.get("codigo", "")))
            r.cells[1].paragraphs[0].add_run(str(s.get("nombre", "")))
            r.cells[2].paragraphs[0].add_run(str(s.get("categoria", "")))
            r.cells[3].paragraphs[0].add_run(f"{s.get('altitud', 0):.0f} m")
            r.cells[4].paragraphs[0].add_run(str(s.get("municipio", "")))
            r.cells[5].paragraphs[0].add_run(f"{s.get('distancia_km', 0):.1f} km")
        _format_table(t_st, [1.1, 1.8, 1.3, 0.8, 1.1, 0.8])
    add_fig("stations_map", "Ubicación espacial de las estaciones meteorológicas del IDEAM en el entorno de la cuenca.")

    # 8. Polígonos de Thiessen
    add_h1("8. Análisis Pluviométrico y Polígonos de Thiessen")
    th_weights = summary.get("thiessen_weights") or []
    if th_weights:
        t_th = doc.add_table(rows=1, cols=4)
        t_th.rows[0].cells[0].paragraphs[0].add_run("Código")
        t_th.rows[0].cells[1].paragraphs[0].add_run("Estación Meteorológica")
        t_th.rows[0].cells[2].paragraphs[0].add_run("Área de Influencia (km²)")
        t_th.rows[0].cells[3].paragraphs[0].add_run("% Área Cuenca")
        for th in th_weights:
            r = t_th.add_row()
            r.cells[0].paragraphs[0].add_run(str(th.get("codigo", "")))
            r.cells[1].paragraphs[0].add_run(str(th.get("nombre", "")))
            r.cells[2].paragraphs[0].add_run(f"{th.get('area_km2', 0):.2f}")
            r.cells[3].paragraphs[0].add_run(f"{th.get('porcentaje', 0):.1f}%")
        _format_table(t_th, [1.3, 2.5, 1.5, 1.3])
    add_fig("thiessen_map", "Polígonos de Thiessen y áreas de influencia pluviométrica sobre la cuenca.")

    # 9. Curvas IDF
    add_h1("9. Curvas Intensidad – Duración – Frecuencia (IDF)")
    doc.add_paragraph("Ecuación regional paramétrica del IDEAM: I = (a · Tr^b) / (d + c)^k.")
    add_fig("idf_curves", "Curvas Intensidad–Duración–Frecuencia (IDF) calculadas para la cuenca.")

    # 10. Suelos y CN
    add_h1("10. Caracterización Hidrológica del Suelo y Número de Curva (SCS-CN)")
    cn_data = summary.get("curve_number") or {}
    cn_units = cn_data.get("units") or []
    if cn_units:
        t_cn = doc.add_table(rows=1, cols=6)
        t_cn.rows[0].cells[0].paragraphs[0].add_run("Cobertura")
        t_cn.rows[0].cells[1].paragraphs[0].add_run("Uso SCS")
        t_cn.rows[0].cells[2].paragraphs[0].add_run("Grupo")
        t_cn.rows[0].cells[3].paragraphs[0].add_run("CN")
        t_cn.rows[0].cells[4].paragraphs[0].add_run("Área (km²)")
        t_cn.rows[0].cells[5].paragraphs[0].add_run("CN × A")
        for u in cn_units:
            r = t_cn.add_row()
            r.cells[0].paragraphs[0].add_run(str(u.get("cobertura", "")))
            r.cells[1].paragraphs[0].add_run(str(u.get("uso_scs", "")))
            r.cells[2].paragraphs[0].add_run(str(u.get("grupo_suelo", "")))
            r.cells[3].paragraphs[0].add_run(str(u.get("cn", "")))
            r.cells[4].paragraphs[0].add_run(f"{u.get('area_km2', 0):.2f}")
            r.cells[5].paragraphs[0].add_run(f"{u.get('nc_ai', 0):.2f}")
        _format_table(t_cn, [1.8, 1.4, 0.7, 0.6, 1.1, 1.0])
    doc.add_paragraph(f"Número de Curva Ponderado adoptado: CN = {summary.get('cn_weighted', 75):.1f}.")
    add_fig("curve_number", "Distribución de coberturas de suelo y Número de Curva ponderado.")

    # 11. Caudales Máximos
    add_h1("11. Modelación Hidrológica y Caudales Máximos de Diseño")
    peak_flows = summary.get("peak_discharges") or []
    if peak_flows:
        t_q = doc.add_table(rows=1, cols=6)
        t_q.rows[0].cells[0].paragraphs[0].add_run("Periodo Retorno")
        t_q.rows[0].cells[1].paragraphs[0].add_run("Idiseño (mm/h)")
        t_q.rows[0].cells[2].paragraphs[0].add_run("Ptotal (mm)")
        t_q.rows[0].cells[3].paragraphs[0].add_run("QRacional (m³/s)")
        t_q.rows[0].cells[4].paragraphs[0].add_run("QSCS (m³/s)")
        t_q.rows[0].cells[5].paragraphs[0].add_run("QDiseño (m³/s)")
        for q in peak_flows:
            r = t_q.add_row()
            r.cells[0].paragraphs[0].add_run(f"Tr = {q['tr_anos']} años")
            r.cells[1].paragraphs[0].add_run(f"{q['intensidad_mm_h']:.1f}")
            r.cells[2].paragraphs[0].add_run(f"{q['precipitacion_total_mm']:.1f}")
            r.cells[3].paragraphs[0].add_run(f"{q['caudal_racional_m3_s']:.2f}")
            r.cells[4].paragraphs[0].add_run(f"{q['caudal_scs_m3_s']:.2f}")
            r.cells[5].paragraphs[0].add_run(f"{q['caudal_diseno_m3_s']:.2f}")
        _format_table(t_q, [1.4, 1.1, 1.0, 1.2, 1.1, 1.2])
    add_fig("hydrographs", "Hidrogramas de caudal de diseño para diferentes periodos de retorno.")

    # 12. Cauce Principal y Perfil
    add_h1("12. Características del Cauce Principal y Perfil Longitudinal")
    desnivel = (summary.get("main_channel_elevation_source_m") or 0) - (summary.get("main_channel_elevation_outlet_m") or 0)
    t_ch = doc.add_table(rows=1, cols=2)
    t_ch.rows[0].cells[0].paragraphs[0].add_run("Parámetro del Cauce")
    t_ch.rows[0].cells[1].paragraphs[0].add_run("Valor")
    ch_data = [
        ("Longitud del Cauce Principal (L)", f"{summary.get('main_channel_length_km', 0):.2f} km"),
        ("Elevación en Cabecera", f"{summary.get('main_channel_elevation_source_m', 0):.2f} msnm"),
        ("Elevación en Exutorio", f"{summary.get('main_channel_elevation_outlet_m', 0):.2f} msnm"),
        ("Desnivel Topográfico (ΔH)", f"{desnivel:.2f} m"),
        ("Pendiente Media (S)", f"{summary.get('main_channel_slope_percent', 0):.3f}%"),
    ]
    for label, val in ch_data:
        r = t_ch.add_row()
        r.cells[0].paragraphs[0].add_run(label)
        r.cells[1].paragraphs[0].add_run(val)
    _format_table(t_ch, [4.2, 2.4])
    add_fig("profile", "Perfil longitudinal altimétrico del cauce principal.")

    # 13. Subcuencas
    add_h1("13. Análisis Morfométrico y Caracterización de Subcuencas")
    doc.add_paragraph(f"Se identificaron {summary.get('subbasin_count', 0)} subcuencas tributarias sobre la red de drenaje.")
    add_fig("subbasins", "Subdivisión en subcuencas hidrológicas, red de drenaje y cauce principal.")

    # 14. Conclusiones
    add_h1("14. Conclusiones y Recomendaciones")
    doc.add_paragraph(
        f"• Se delimitó exitosamente la cuenca aportante para {site}, abarcando un área total de {summary.get('area_km2', 0):.2f} km² y un perímetro de {summary.get('perimetro_km', 0):.2f} km.\n"
        f"• El tiempo de concentración medio adoptado es de {tc_p * 60:.1f} minutos ({tc_p:.2f} h).\n"
        f"• El Número de Curva ponderado estimado (CN = {summary.get('cn_weighted', 75):.1f}) representa las coberturas y suelos de la cuenca.\n"
        f"• Los caudales máximos de diseño modelados para Tr de 25, 50 y 100 años corresponden a "
        f"{peak_flows[3]['caudal_diseno_m3_s'] if len(peak_flows)>3 else 0:.2f} m³/s, "
        f"{peak_flows[4]['caudal_diseno_m3_s'] if len(peak_flows)>4 else 0:.2f} m³/s y "
        f"{peak_flows[5]['caudal_diseno_m3_s'] if len(peak_flows)>5 else 0:.2f} m³/s respectivamente."
    )

    # 15. Limitaciones
    add_h1("15. Limitaciones Técnicas")
    doc.add_paragraph(
        "Los resultados derivan del procesamiento topográfico de modelos de elevación satelitales y formulaciones hidrológicas sintéticas. "
        "El presente estudio no reemplaza levantamientos batimétricos directos en el cauce ni la verificación estructural en campo de las obras de paso existentes."
    )

    # 16. Anexo A: Series y Tratamiento Pluviométrico
    add_h1("16. Anexo A — Series Hidrometeorológicas y Tratamiento de Información")
    doc.add_paragraph(
        "En este anexo se presenta el registro de información histórica de las estaciones meteorológicas del IDEAM seleccionadas para el área de influencia del proyecto, "
        "junto con la metodología aplicada para la verificación, consistencia y completación de series climáticas."
    )
    add_h2("Metodología de Tratamiento y Completación de Datos Pluviométricos")
    doc.add_paragraph(
        "Para el análisis de consistencia y completación de registros faltantes en las estaciones pluviométricas se aplican los métodos estandarizados por el IDEAM "
        "y la Organización Meteorológica Mundial (OMM No. 168):\n\n"
        "1. Método de Proporciones Normales (Normal Ratio Method): Aplicado cuando la precipitación media anual de las estaciones vecinas difiere en más de un 10% de la estación bajo análisis.\n"
        "2. Regresión Lineal y Correlación Cruzada: Empleada entre estaciones con coeficiente de determinación R² > 0.75 y regímenes pluviométricos homogéneos.\n"
        "3. Interpolación Ponderada por Inverso de la Distancia (IDW): Utilizada para interpolar campos continuos de lluvia a partir de la red de pluviómetros circundantes."
    )

    doc.save(str(output_docx))
    return output_docx
