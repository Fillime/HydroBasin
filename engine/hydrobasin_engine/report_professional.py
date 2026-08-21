from __future__ import annotations

import math
import shutil
import subprocess
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

from .export_excel import export_ideam_and_hydrology_excel
from .latex_to_docx import convert_latex_to_docx
from .location import location_label, resolve_administrative_location
from .plan_drawing import generar_plano_pdf
from .report_docx import generar_informe_docx


def _esc(value: object) -> str:
    if value is None or value == "":
        return "N/D"
    text = str(value)
    repl = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    for old, new in repl.items():
        text = text.replace(old, new)
    return text


def _n(val: object, decimals: int = 2) -> str:
    if val is None:
        return "N/D"
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return "N/D"
        return f"{v:.{decimals}f}"
    except (ValueError, TypeError):
        return str(val) if str(val).strip() else "N/D"


def _tc_min(summary: dict, key: str) -> float:
    raw = summary.get(key)
    if raw is None:
        return 60.0
    try:
        v = float(raw)
        return v * 60.0 if v < 10.0 else v
    except Exception:
        return 60.0


def _site(summary: dict, loc: dict) -> str:
    proj = (summary.get("project_name") or "").strip()
    if proj:
        return proj
    return "Cuenca Hidrográfica"


def _admin_label(loc: dict) -> str:
    return location_label(loc)


def _satellite_map(output_dir: Path, summary: dict, loc: dict) -> str | None:
    outlet = summary.get("outlet_original") or {}
    lat = float(outlet.get("y", 0))
    lon = float(outlet.get("x", 0))
    if abs(lat) < 1e-6 and abs(lon) < 1e-6:
        return None
    dlat = 0.08
    dlng = 0.08
    bbox = f"{lon - dlng},{lat - dlat},{lon + dlng},{lat + dlat}"
    params = urlencode({
        "bbox": bbox,
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "1400,850",
        "format": "png32",
        "transparent": "false",
        "f": "image",
    })
    try:
        req = Request(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + params,
            headers={"User-Agent": "HydroBasin/1.0"},
        )
        with urlopen(req, timeout=25) as response:
            image = plt.imread(BytesIO(response.read()), format="png")
        fig, ax = plt.subplots(figsize=(10.5, 5.8))
        ax.imshow(image, extent=[lon - dlng, lon + dlng, lat - dlat, lat + dlat])
        ax.scatter([lon], [lat], s=140, facecolor="#ef4444", edgecolor="white", linewidth=2.2, zorder=4)
        ax.annotate(
            "Punto de Aforo (Exutorio)",
            (lon, lat),
            xytext=(10, 10),
            textcoords="offset points",
            color="white",
            fontsize=9.5,
            fontweight="bold",
            bbox={"boxstyle": "round,pad=.3", "fc": "#111827", "alpha": 0.85, "ec": "#1f9d8f", "lw": 1.2},
        )
        ax.set_title(f"Localización Satelital Regional -- {_admin_label(loc)}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Longitud (WGS84)", fontsize=9)
        ax.set_ylabel("Latitud (WGS84)", fontsize=9)
        ax.grid(True, color="white", alpha=0.3, linestyle="--", linewidth=0.5)
        path = output_dir / "figuras" / "00_ubicacion_satelital.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return "figuras/00_ubicacion_satelital.png"
    except Exception:
        return None


def _subbasin_table_rows(subbasins, total_area: float, limit=15) -> str:
    if subbasins is None or subbasins.empty or "area_km2" not in subbasins.columns:
        return ""
    top = subbasins.sort_values("area_km2", ascending=False).head(limit)
    rows = []
    for _, r in top.iterrows():
        area = float(r["area_km2"])
        pct = (area / total_area * 100.0) if total_area > 0 else 0.0
        rows.append(rf"{int(r['subbasin_id'])} & {_n(area, 2)} & {_n(pct, 1)}\% \\")
    return "\n".join(rows)


def _fig_path(output_dir: Path, rel_or_abs: str | None) -> str | None:
    if not rel_or_abs:
        return None
    p = Path(rel_or_abs)
    if p.is_absolute():
        if p.exists():
            return str(p).replace("\\", "/")
        return None
    if (output_dir / rel_or_abs).exists():
        return rel_or_abs.replace("\\", "/")
    return None


def _report(output_dir: Path, summary: dict, figures: dict[str, str], subbasins, loc: dict) -> str:
    site = _site(summary, loc)
    admin = _admin_label(loc)
    outlet = summary.get("outlet_original") or {}
    total_area = float(summary.get("area_km2") or 1.0)

    # Figuras completas verificadas
    sat = _fig_path(output_dir, figures.get("location_satellite"))
    dem_fig = _fig_path(output_dir, figures.get("dem"))
    hillshade_fig = _fig_path(output_dir, figures.get("hillshade"))
    fdir_fig = _fig_path(output_dir, figures.get("flow_direction"))
    acc_fig = _fig_path(output_dir, figures.get("accumulation"))
    watershed_fig = _fig_path(output_dir, figures.get("watershed"))
    strahler_fig = _fig_path(output_dir, figures.get("strahler"))
    subfig = _fig_path(output_dir, figures.get("subbasins"))
    profile = _fig_path(output_dir, figures.get("profile"))
    st_fig = _fig_path(output_dir, figures.get("stations_map"))
    thiessen_fig = _fig_path(output_dir, figures.get("thiessen_map"))
    idf_fig = _fig_path(output_dir, figures.get("idf_curves"))
    corine_fig = _fig_path(output_dir, figures.get("corine_landcover"))
    hsg_fig = _fig_path(output_dir, figures.get("hydrologic_soils"))
    cn_fig = _fig_path(output_dir, figures.get("curve_number"))
    hydro_fig = _fig_path(output_dir, figures.get("hydrographs"))

    client = summary.get("client") or "Particular"
    calc = summary.get("calculated_by") or "Elaboración técnica"
    rev = summary.get("reviewed_by") or "Revisión Técnica"

    tc_k, tc_t, tc_p = (_tc_min(summary, k) for k in ("tc_kirpich_h", "tc_temez_h", "tc_promedio_h"))
    desnivel = (summary.get("main_channel_elevation_source_m") or 0) - (summary.get("main_channel_elevation_outlet_m") or 0)
    cota_ex = summary.get("main_channel_elevation_outlet_m") or summary.get("elevacion_min_m")
    cota_ex_str = f"{cota_ex:.1f} msnm" if cota_ex is not None else "N/D"

    # Fórmulas de Tiempo de Concentración
    L_km = float(summary.get("main_channel_length_km") or 1.0)
    S_pct = float(summary.get("main_channel_slope_percent") or 1.0)
    S_m_m = max(0.0001, S_pct / 100.0)
    S_m_km = max(0.1, S_m_m * 1000.0)

    tc_giandotti_h = (4.0 * math.sqrt(total_area) + 1.5 * L_km) / (25.3 * math.sqrt(L_km * S_m_m)) if (L_km * S_m_m) > 0 else (summary.get("tc_kirpich_h") or 1.0)
    tc_johnstone_h = 2.6 * math.pow(L_km / math.sqrt(S_m_km), 0.5) if S_m_km > 0 else (summary.get("tc_kirpich_h") or 1.0)
    tc_chow_h = 0.273 * math.pow(L_km / math.sqrt(S_m_m), 0.64) if S_m_m > 0 else (summary.get("tc_kirpich_h") or 1.0)
    H_m = max(0.01, abs(desnivel))
    tc_scs_h = 0.947 * math.pow((L_km ** 3) / H_m, 0.385) if H_m > 0 else None
    tc_heras_h = 0.30 * math.pow(L_km / math.pow(max(S_pct, 0.0001), 0.25), 0.76)
    tc_cuerpo_h = 0.28 * math.pow(L_km / math.pow(max(S_m_m, 0.0001), 0.25), 0.76)

    tc_methods = [
        ("Kirpich California", summary.get("tc_kirpich_h") or 1.0),
        ("Témez", summary.get("tc_temez_h") or 1.0),
        ("Johnstone y Cross", tc_johnstone_h),
        ("Giandotti", tc_giandotti_h),
        ("SCS", tc_scs_h),
        ("Ventura-Heras", tc_heras_h),
        ("V.T. Chow", tc_chow_h),
        ("Cuerpo de Ingenieros", tc_cuerpo_h),
    ]
    tc_avg_h = sum(v for _, v in tc_methods) / len(tc_methods)
    tc_avg_min = tc_avg_h * 60.0

    tc_rows = "\n".join(
        rf"{name} & {_n(val, 2)} h & {_n(val * 60.0, 1)} min \\"
        for name, val in tc_methods
    )

    # 1. Tabla de Estaciones IDEAM
    stations = summary.get("ideam_stations") or []
    st_rows = []
    for s in stations[:8]:
        muni = s.get("municipio") or admin.split(",")[0]
        st_rows.append(
            rf"{_esc(s.get('codigo'))} & {_esc(s.get('nombre'))} & {_esc(s.get('categoria'))} & {_n(s.get('altitud'), 0)} m & {_n(s.get('latitud'), 4)}$^\circ$ & {_n(s.get('longitud'), 4)}$^\circ$ & {_esc(muni)} & {_n(s.get('distancia_km'), 1)} km \\"
        )
    st_table_tex = "\n".join(st_rows) if st_rows else r"\multicolumn{8}{c}{No se registraron estaciones en el radio de búsqueda} \\"

    # 2. Tabla de Polígonos de Thiessen
    thiessen_weights = summary.get("thiessen_weights") or []
    th_rows = []
    for th in thiessen_weights:
        th_rows.append(rf"{_esc(th.get('codigo'))} & {_esc(th.get('nombre'))} & {_n(th.get('area_km2'))} & {_n(th.get('porcentaje'), 1)}\% \\")
    th_table_tex = "\n".join(th_rows) if th_rows else r"\multicolumn{4}{c}{Ponderación uniforme sobre la cuenca} \\"

    # 3. Tabla de Unidades de Cobertura y CN
    cn_data = summary.get("curve_number") or {}
    cn_units = cn_data.get("units") or []

    cn_grouped = {}
    for u in cn_units:
        key = (
            str(u.get("cobertura") or "N/D").strip(),
            str(u.get("uso_scs") or "N/D").strip(),
            str(u.get("condicion") or "N/D").strip(),
            str(u.get("grupo_suelo") or "N/D").strip(),
            u.get("cn"),
        )
        if key not in cn_grouped:
            cn_grouped[key] = {
                "cobertura": key[0], "uso_scs": key[1], "condicion": key[2],
                "grupo_suelo": key[3], "cn": key[4], "area_km2": 0.0, "nc_ai": 0.0
            }
        cn_grouped[key]["area_km2"] += float(u.get("area_km2") or 0.0)
        cn_grouped[key]["nc_ai"] += float(u.get("nc_ai") or 0.0)

    cn_report_units = sorted(cn_grouped.values(), key=lambda x: x["area_km2"], reverse=True)

    cn_rows = [
        rf"{_esc(u.get('cobertura'))} & {_esc(u.get('uso_scs'))} & {_esc(u.get('condicion'))} & "
        rf"{_esc(u.get('grupo_suelo'))} & {_n(u.get('cn'),0)} & {_n(u.get('area_km2'))} & {_n(u.get('nc_ai'))} \\"
        for u in cn_report_units
    ]
    cn_table_tex = "\n".join(cn_rows) if cn_rows else r"\multicolumn{7}{c}{No se dispone de unidades clasificadas} \\"

    landcover_seen = {}
    for u in cn_report_units:
        landcover_seen[(u["cobertura"], u["uso_scs"], u["condicion"])] = True
    cn_landcover_table_tex = "\n".join(
        rf"{_esc(cob)} & {_esc(uso)} & {_esc(cond)} \\"
        for cob, uso, cond in sorted(landcover_seen.keys(), key=lambda x: x[0])
    ) or r"\multicolumn{3}{c}{No se dispone de coberturas reclasificadas} \\"

    geology_seen = {}
    for u in cn_units:
        lit = str(u.get("litologia") or "N/D").strip()
        hsg = str(u.get("grupo_suelo") or "N/D").strip()
        if lit != "N/D" or hsg != "N/D":
            geology_seen[(lit, hsg)] = True
    cn_geology_table_tex = "\n".join(
        rf"{_esc(lit)} & {_esc(hsg)} \\"
        for lit, hsg in sorted(geology_seen.keys(), key=lambda x: x[0])
    ) or r"\multicolumn{2}{c}{No se dispone de unidades litológicas reclasificadas} \\"

    cn_weighted_report = cn_data.get("cn_weighted")
    if cn_weighted_report is None:
        cn_weighted_report = summary.get("cn_weighted")

    # 4. Tabla de Caudales Máximos por Periodo de Retorno (Tr)
    peak_flows = summary.get("peak_discharges") or []
    q_rows = []
    for q in peak_flows:
        q_rows.append(
            rf"Tr = {q['tr_anos']} años & {_n(q['intensidad_mm_h'], 1)} & {_n(q['precipitacion_total_mm'], 1)} & {_n(q['precipitacion_efectiva_mm'], 1)} & {_n(q['caudal_racional_m3_s'])} & {_n(q['caudal_scs_m3_s'])} & \textbf{{{_n(q['caudal_diseno_m3_s'])}}} \\"
        )
    q_table_tex = "\n".join(q_rows)

    # 5. Tabla de Subcuencas
    sub_rows = _subbasin_table_rows(subbasins, total_area)

    # 6. Tabla Anexo IDEAM con datos reales
    anexo_ideam_rows = []
    for s in stations:
        codigo = _esc(s.get("codigo"))
        nombre = _esc(s.get("nombre"))
        cat = _esc(s.get("categoria"))
        alt = f"{_n(s.get('altitud'), 0)} m"
        lat_str = rf"{_n(s.get('latitud'), 4)}$^\circ$"
        lon_str = rf"{_n(s.get('longitud'), 4)}$^\circ$"
        muni = _esc(s.get("municipio") or admin.split(",")[0])
        dist = f"{_n(s.get('distancia_km'), 1)} km"
        oper = _esc(s.get("estado") or "Activa")
        anexo_ideam_rows.append(
            rf"{codigo} & {nombre} & {cat} & {alt} & {lat_str} & {lon_str} & {muni} & {dist} & {oper} \\"
        )
    anexo_ideam_tex = "\n".join(anexo_ideam_rows) if anexo_ideam_rows else r"\multicolumn{9}{c}{N/D} \\"

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish,es-tabla]{{babel}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{xcolor}}
\usepackage{{fancyhdr}}
\usepackage{{array}}
\usepackage{{amsmath}}
\usepackage{{caption}}

% Espaciado compacto y consistente entre tablas/figuras y el texto
\setlength{{\textfloatsep}}{{10pt plus 2pt minus 2pt}}
\setlength{{\floatsep}}{{10pt plus 2pt minus 2pt}}
\setlength{{\intextsep}}{{10pt plus 2pt minus 2pt}}
\setlength{{\abovecaptionskip}}{{4pt}}
\setlength{{\belowcaptionskip}}{{4pt}}

% Fuente dentro del mismo flotante, con separación controlada
\newcommand{{\fuente}}[1]{{%
  \par\vspace{{-0.25em}}%
  {{\raggedright\footnotesize\textit{{Fuente: #1}}\par}}%
  \vspace{{0.65em}}%
}}


\geometry{{margin=2.2cm}}
\definecolor{{hbaccent}}{{HTML}}{{1F9D8F}}
\definecolor{{hbprimary}}{{HTML}}{{176B73}}

\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{Estudio Hidrológico}}
\rhead{{Informe Técnico}}
\cfoot{{\thepage}}

\setcounter{{tocdepth}}{{2}}
\setcounter{{secnumdepth}}{{2}}

\renewcommand{{\listfigurename}}{{Índice de Figuras}}
\renewcommand{{\listtablename}}{{Índice de Tablas}}

\begin{{document}}

% ============================== PORTADA FORMAL ==============================
\begin{{titlepage}}
\vspace*{{0.8cm}}
\noindent
\begin{{tabular}}{{|p{{4.2cm}}|p{{8.0cm}}|p{{3.4cm}}|}}\hline
\textbf{{\color{{hbaccent}}HYDROBASIN STUDIO}} & \textbf{{ESTUDIO HIDROLÓGICO Y MORFOMÉTRICO}} \newline \small {_esc(site)} & \small Versión 1.0 \newline {datetime.now().strftime('%d/%m/%Y')} \\\hline
\end{{tabular}}\\[2.0cm]

\begin{{center}}
{{\Huge\bfseries INFORME DE DELIMITACIÓN Y CARACTERIZACIÓN MORFOMÉTRICA DE CUENCA}}\\[0.6cm]
{{\Large\bfseries {_esc(site)}}}\\[0.3cm]
{{\normalsize {_esc(admin)}}}\\[2.2cm]

\textbf{{RELACIÓN DE REVISIÓN Y AUTORÍA}}\\[3mm]
\begin{{tabular}}{{|p{{4.5cm}}|p{{5.0cm}}|p{{4.5cm}}|}}\hline
\textbf{{ELABORÓ:}} & \textbf{{REVISÓ:}} & \textbf{{FECHA:}} \\\hline
{_esc(calc)} & {_esc(rev)} & {datetime.now().strftime('%d/%m/%Y')} \\\hline
\multicolumn{{2}}{{|l|}}{{\textbf{{CLIENTE / ENTIDAD:}} {_esc(client)}}} & \textbf{{ESTADO:}} Aprobado \\\hline
\end{{tabular}}
\end{{center}}

\vfill
\noindent
{{\footnotesize Documento técnico de ingeniería hidrológica.}}
\end{{titlepage}}

% ============================== ÍNDICES ==============================
\tableofcontents
\vspace{{0.6cm}}
\listoffigures
\vspace{{0.6cm}}
\listoftables
\newpage

% ============================== 1. INTRODUCCIÓN ==============================
\section{{Introducción}}
El presente documento corresponde al informe técnico del estudio hidrológico y geomorfológico desarrollado para el proyecto \textbf{{{_esc(site)}}}, localizado en el municipio de \textbf{{{_esc(admin)}}}. El estudio comprende la delimitación precisa de la divisoria de aguas, caracterización física de la cuenca, consulta y análisis de la red de estaciones meteorológicas oficiales del IDEAM, cálculo de polígonos de Thiessen, curvas Intensidad--Duración--Frecuencia (IDF), determinación del Número de Curva SCS (CN) y modelación de hidrogramas y caudales máximos de escorrentía para diversos periodos de retorno.

% ============================== 2. OBJETIVOS Y ALCANCE ==============================
\section{{Objetivos y Alcance}}

\subsection{{Objetivo General}}
Delimitar y caracterizar geomorfológica e hidrológicamente la cuenca aportante al punto de interés del proyecto \textbf{{{_esc(site)}}}, determinando sus parámetros morfométricos, red de drenaje, tiempos de concentración y caudales de diseño hacia el exutorio.

\subsection{{Objetivos Específicos}}
\begin{{itemize}}
\item Delimitar la cuenca hidrográfica y su red de drenaje a partir de modelos de elevación digital corregidos hidrológicamente.
\item Calcular los parámetros morfométricos de forma, relieve y red fluvial (Horton, Gravelius, Miller, Strahler).
\item Subdividir la cuenca en subcuencas tributarias y caracterizar el cauce principal con su perfil altimétrico.
\item Consultar la red pluviométrica del IDEAM en el área de influencia y ponderar su representatividad mediante Polígonos de Thiessen.
\item Formular las curvas IDF y determinar el Número de Curva ponderado (SCS-CN) a partir de coberturas y suelos.
\item Estimar los tiempos de concentración y modelar los caudales máximos de diseño para periodos de retorno de 2.33, 5, 10, 25, 50 y 100 años.
\end{{itemize}}

\subsection{{Alcance del Estudio}}
El alcance comprende el análisis geomorfométrico automatizado, la modelación hidrometeorológica regional con datos oficiales del IDEAM y la formulación hidrológica mediante el método del Hidrograma Unitario del SCS y el Método Racional para el dimensionamiento de obras civiles y manejo de aguas.

% ============================== 3. LOCALIZACIÓN ==============================
\section{{Localización y Ubicación General}}
Las actividades que engloban el estudio se localizan en la jurisdicción de \textbf{{{_esc(admin)}}}. El punto de cierre o exutorio fijado para la cuenca se ubica en las coordenadas geográficas \textbf{{{_n(outlet.get('y'),6)}$^\circ$ Latitud Norte, {_n(outlet.get('x'),6)}$^\circ$ Longitud Oeste}} (WGS84), a una cota de \textbf{{{_esc(cota_ex_str)}}}.

En la Figura~\ref{{fig:satelite}} se ilustra la localización regional del área de estudio sobre imagen satelital con la posición del punto de aforo.

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.86\textwidth,height=0.34\textheight,keepaspectratio]{{{sat}}}
\caption{{Localización regional del área de estudio sobre imagen satelital Esri World Imagery.}}
\label{{fig:satelite}}
\end{{figure}}
''' if sat else ''}

% ============================== 4. INFORMACIÓN TOPOGRÁFICA ==============================
\section{{Información Topográfica y Acondicionamiento del Terreno}}
La caracterización geomorfológica se fundamentó en el Modelo Digital de Elevación (DEM) \textit{{{_esc(summary.get('dem_source') or 'DEM Satelital')}}}, con una resolución métrica de {_n((summary.get('metric_resolution_m') or [30])[0], 1)} m. Para asegurar la continuidad física del escurrimiento, la superficie topográfica fue sometida a un acondicionamiento hidrológico mediante el relleno de depresiones cerradas (\textit{{sinks/pits}}) y corrección de zonas planas, garantizando una pendiente continua hacia el punto de descarga.

Sobre el terreno corregido se determinaron las direcciones de flujo empleando el esquema determinístico D8 y se construyó la matriz de acumulación de celdas aportantes, a partir de la cual se ajustó la posición del exutorio al eje principal de concentración fluvial.

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.78\textwidth,height=0.28\textheight,keepaspectratio]{{{dem_fig}}}
\caption{{Contexto regional del Modelo Digital de Elevación (DEM).}}
\label{{fig:dem}}
\end{{figure}}
''' if dem_fig else ''}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.78\textwidth,height=0.28\textheight,keepaspectratio]{{{hillshade_fig}}}
\caption{{Relieve sombreado (\textit{{Hillshade}}) del área de estudio.}}
\label{{fig:hillshade}}
\end{{figure}}
''' if hillshade_fig else ''}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.78\textwidth,height=0.28\textheight,keepaspectratio]{{{fdir_fig}}}
\caption{{Dirección de flujo D8 dentro de la cuenca.}}
\label{{fig:fdir}}
\end{{figure}}
''' if fdir_fig else ''}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.78\textwidth,height=0.28\textheight,keepaspectratio]{{{acc_fig}}}
\caption{{Acumulación de flujo dentro de la cuenca aportante.}}
\label{{fig:acc}}
\end{{figure}}
''' if acc_fig else ''}

% ============================== 5. CARACTERIZACIÓN MORFOMÉTRICA ==============================
\section{{Caracterización Morfométrica de la Cuenca}}

\subsection{{Área, Perímetro y Longitud Axial}}
A partir del análisis espacial de la cuenca delimitada se calcularon los parámetros geométricos, morfométricos y de relieve resumidos en el Cuadro~\ref{{tab:morfometria}}.

\begin{{table}}[H]
\centering
\caption{{Parámetros morfométricos y de relieve de la cuenca.}}
\label{{tab:morfometria}}
\begin{{tabular}}{{p{{8.5cm}}r}}\toprule
\textbf{{Parámetro Morfométrico}} & \textbf{{Valor Obtenido}} \\\midrule
Área de la Cuenca ($A$) & \textbf{{{_n(summary.get('area_km2'))} km$^2$}} \\
Perímetro de la Cuenca ($P$) & \textbf{{{_n(summary.get('perimetro_km'))} km}} \\
Longitud Axial ($L_a$) & {_n(summary.get('longitud_axial_km'))} km \\
Factor de Forma de Horton ($K_f$) & {_n(summary.get('factor_forma'),3)} \\
Coeficiente de Compacidad de Gravelius ($K_c$) & {_n(summary.get('coeficiente_compacidad'),3)} \\
Relación de Circularidad de Miller ($R_c$) & {_n(summary.get('relacion_circularidad'),3)} \\
Densidad de Drenaje ($D_d$) & {_n(summary.get('densidad_drenaje_km_km2'),3)} km/km$^2$ \\
Orden Máximo de Corrientes (Strahler) & {summary.get('strahler_max','N/D')} \\
Número de Subcuencas Identificadas & {summary.get('subbasin_count','N/D')} \\
Elevación Mínima (Exutorio) & {_n(summary.get('elevacion_min_m'))} msnm \\
Elevación Máxima (Cabecera) & {_n(summary.get('elevacion_max_m'))} msnm \\
Elevación Media de la Cuenca & {_n(summary.get('elevacion_media_m'))} msnm \\
Relieve Total de la Cuenca ($H_T$) & {_n(summary.get('relieve_cuenca_m'))} m \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Factor de Forma}}

El factor de forma expresa la relación existente entre el área de la cuenca y el cuadrado de su longitud máxima. La longitud máxima se determina siguiendo el curso de agua más largo desde la desembocadura hasta la cabecera más distante de la unidad hidrográfica.

\begin{{equation}}
K_f = \frac{{A}}{{L^2}}
\end{{equation}}

Donde:

$K_f$: Factor de forma, adimensional.

$L$: Longitud máxima de la cuenca, en km.

$A$: Área de la cuenca, en km$^2$.

Los valores del factor de forma y la clasificación del mismo se presentan a continuación.

\begin{{table}}[H]
\centering
\caption{{Formas de la cuenca según el valor de $K_f$.}}
\label{{tab:kf_clasificacion}}
\begin{{tabular}}{{ll}}\toprule
\textbf{{$K_f$}} & \textbf{{Clasificación}} \\\midrule
$<0.22$ & Muy alargada \\
0.22--0.30 & Alargada \\
0.30--0.37 & Ligeramente alargada \\
0.37--0.45 & Ni alargada ni ensanchada \\
0.45--0.60 & Ensanchada ligeramente \\
0.60--0.80 & Ensanchada \\
0.80--1.20 & Muy ensanchada \\
$>1.20$ & Rodeando el desagüe \\
\bottomrule
\end{{tabular}}
\fuente{{Adaptado de Cortolima -- Caracterización Morfométrica del río Totare.}}
\end{{table}}

Para la cuenca evaluada se obtuvo un valor de $K_f = {_n(summary.get('factor_forma'),3)}$.

\subsection{{Índice de Gravelius}}

Este coeficiente es la relación entre el perímetro de la cuenca y el perímetro de un círculo equivalente; se define como la razón entre el perímetro de la cuenca, que corresponde con la misma longitud de la divisoria que la encierra, y el perímetro de la circunferencia. Este coeficiente adimensional es independiente del área estudiada y tiene por definición un valor igual a 1 para cuencas imaginarias de forma exactamente circular. Los valores del coeficiente de compacidad no son inferiores a uno. Los valores más cercanos a uno indican una cuenca semejante a una circunferencia; por el contrario, entre más alejados estén de la unidad, corresponderán a cuencas alargadas.

El cálculo del coeficiente de compacidad se determina por medio de la siguiente expresión:

\begin{{equation}}
K_c = 0.28 \frac{{P}}{{\sqrt{{A}}}}
\end{{equation}}

Donde:

$K_c$: Índice de compacidad, adimensional.

$P$: Perímetro de la cuenca, en km.

$A$: Área de drenaje de la cuenca, en km$^2$.

En la siguiente tabla se presentan las categorías para la clasificación de las cuencas de acuerdo con el coeficiente de compacidad obtenido y su relación con la potencialidad a eventos torrenciales.

\begin{{table}}[H]
\centering
\caption{{Relación entre el índice de Gravelius y la torrencialidad.}}
\label{{tab:gravelius_clasificacion}}
\begin{{tabular}}{{p{{3cm}}p{{5cm}}p{{7cm}}}}\toprule
\textbf{{Valores de $K_c$}} & \textbf{{Forma}} & \textbf{{Clasificación}} \\\midrule
1.00--1.25 & Redonda a oval redonda & Mayor susceptibilidad relativa a concentraciones rápidas del escurrimiento. \\
1.25--1.50 & De oval redonda a oval oblonga & Presenta peligros torrenciales, aunque inferiores a la clase anterior. \\
1.50--1.75 & De oval oblonga a rectangular oblonga & Menor riesgo relativo a avenidas torrenciales. \\
\bottomrule
\end{{tabular}}
\fuente{{Adaptado de Cortolima -- Caracterización Morfométrica del río Totare.}}
\end{{table}}

Para la cuenca evaluada se obtuvo un valor de $K_c = {_n(summary.get('coeficiente_compacidad'),3)}$.

\subsection{{Índice de Alargamiento}}

El índice de alargamiento se obtiene por medio de la evaluación de la relación existente entre la mayor longitud de la cuenca y el mayor ancho de la misma. Con este índice, los valores mayores a uno indican cuencas alargadas.

\begin{{equation}}
I_a = \frac{{L_{{max}}}}{{A_{{max}}}}
\end{{equation}}

Donde:

$L_{{max}}$: Longitud máxima de la cuenca, en km.

$A_{{max}}$: Ancho máximo de la cuenca, en km.

La relación del índice de alargamiento permite generar una clasificación geométrica de la cuenca. Este parámetro debe interpretarse de forma conjunta con los demás índices morfométricos, debido a su relación con la concentración temporal de los aportes superficiales.

\subsection{{Relieve y Elevaciones}}
El análisis altimétrico revela una elevación mínima en el exutorio de \textbf{{{_n(summary.get('elevacion_min_m'))} msnm}}, una cota máxima en cabecera de \textbf{{{_n(summary.get('elevacion_max_m'))} msnm}}, y una elevación media ponderada de \textbf{{{_n(summary.get('elevacion_media_m'))} msnm}}, representando un relieve total de $H_T = {_n(summary.get('relieve_cuenca_m'))}$ m.

\subsection{{Orden de Strahler}}
La jerarquización fluvial se realizó bajo la metodología topológica de Strahler, alcanzando un orden máximo de corriente igual a \textbf{{{summary.get('strahler_max','N/D')}}}. En la Figura~\ref{{fig:strahler}} se representa la clasificación espacial de corrientes.

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth,height=0.32\textheight,keepaspectratio]{{{strahler_fig}}}
\caption{{Jerarquía de la red fluvial según el Orden de Corrientes de Strahler.}}
\label{{fig:strahler}}
\end{{figure}}
''' if strahler_fig else ''}

\section{{Tiempo de Concentración}}

El tiempo de concentración de la cuenca se estima a partir de diferentes métodos empíricos comúnmente utilizados en estudios hidrológicos, con el objetivo de contar con un valor representativo para la modelación hidrológica. Este parámetro corresponde al tiempo requerido para que el escurrimiento generado en el punto hidráulicamente más alejado alcance el punto de salida de la cuenca.

En la siguiente tabla se presentan las expresiones matemáticas utilizadas y posteriormente se resumen los resultados obtenidos.

\begin{{table}}[H]
\centering
\caption{{Expresiones matemáticas para tiempos de concentración.}}
\label{{tab:expresiones_tc}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{p{{3cm}}p{{5cm}}p{{8cm}}}}\toprule
\textbf{{Nombre}} & \textbf{{Ecuación}} & \textbf{{Definición de variables}} \\\midrule
Kirpich California & $T_c=0.06628\left(\frac{{L}}{{S^{{0.5}}}}\right)^{{0.77}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $S$: pendiente entre las elevaciones máxima y mínima del cauce principal, m/m. \\
Témez & $T_c=0.30\left(\frac{{L}}{{S^{{0.25}}}}\right)^{{0.76}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $S$: pendiente total del cauce principal, \%. \\
Johnstone y Cross & $T_c=2.6\left(\frac{{L}}{{S^{{0.5}}}}\right)^{{0.5}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $S$: pendiente total del cauce principal, m/km. \\
Giandotti & $T_c=\frac{{4A^{{0.5}}+1.50L}}{{25.3(LS)^{{0.5}}}}$ & $T_c$: tiempo de concentración, h; $A$: área de la cuenca, km$^2$; $L$: longitud del cauce principal, km; $S$: pendiente del cauce principal, m/m. \\
SCS & $T_c=0.947\left(\frac{{L^3}}{{H}}\right)^{{0.385}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $H$: diferencia de cotas entre puntos extremos de la corriente principal, m. \\
Ventura--Heras & $T_c=0.30\left(\frac{{L}}{{S^{{0.25}}}}\right)^{{0.76}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $S$: pendiente total del cauce principal, \%. \\
V.T. Chow & $T_c=0.273\left(\frac{{L}}{{S^{{0.5}}}}\right)^{{0.64}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $S$: pendiente total del cauce principal, m/m. \\
Cuerpo de Ingenieros & $T_c=0.28\left(\frac{{L}}{{S^{{0.25}}}}\right)^{{0.76}}$ & $T_c$: tiempo de concentración, h; $L$: longitud del cauce principal, km; $S$: pendiente total del cauce principal, m/m. \\
\bottomrule
\end{{tabular}}%
}}
\fuente{{Elaboración propia a partir de formulaciones empíricas de uso común en estudios hidrológicos.}}
\end{{table}}

\begin{{table}}[H]
\centering
\caption{{Tiempos de concentración estimados para la cuenca.}}
\label{{tab:tc_resultados}}
\begin{{tabular}}{{lrr}}\toprule
\textbf{{Método}} & \textbf{{$T_c$ (h)}} & \textbf{{$T_c$ (min)}} \\\midrule
{tc_rows}
\midrule
\textbf{{Promedio}} & \textbf{{{_n(tc_avg_h,2)}}} & \textbf{{{_n(tc_avg_min,1)}}} \\
\bottomrule
\end{{tabular}}
\fuente{{Elaboración propia.}}
\end{{table}}

\section{{Caracterización Hidrológica de la Cuenca}}

\subsection{{Método para la estimación de las pérdidas mediante la Curva Numérica del SCS}}

El método de la Curva Numérica del Servicio de Conservación de Suelos (SCS) es un procedimiento hidrológico empírico ampliamente utilizado para estimar la escorrentía directa generada por eventos de lluvia en una cuenca hidrográfica. Este método integra las principales características físicas de la cuenca que influyen en el proceso de escorrentía, tales como el tipo hidrológico de suelo, el uso y cobertura del suelo, el manejo del terreno y la condición antecedente de humedad.

La formulación básica del método se expresa mediante la siguiente relación:

\begin{{equation}}
Q=\frac{{(P-0.2S)^2}}{{P+0.8S}}
\end{{equation}}

Donde:

$Q$: Escorrentía directa o precipitación efectiva.

$P$: Precipitación considerada.

$S$: Diferencia potencial máxima entre $P$ y $Q$ a la hora en que se inicia la tormenta y representa proporcionalmente la pérdida de escorrentía por infiltración, intercepción y almacenamiento superficial.

Los estudios empíricos realizados por el SCS permitieron relacionar la máxima infiltración potencial con un parámetro de referencia denominado Número de Curva, $CN$, cuyos valores están tabulados entre 0 y 100.

\begin{{equation}}
S=\frac{{1000}}{{CN}}-10
\end{{equation}}

Donde:

$CN$: Número de Curva.

$S$: Diferencia potencial máxima entre $P$ y $Q$ a la hora en que se inicia la tormenta y representa proporcionalmente la pérdida de escorrentía por infiltración, intercepción y almacenamiento superficial, expresada en pulgadas.

Para la aplicación en unidades métricas se utiliza:

\begin{{equation}}
S=\frac{{25400}}{{CN}}-254
\end{{equation}}

\subsection{{Tipo de suelo}}

Para la aplicación del método SCS, los suelos se clasifican en uno de los cuatro grupos hidrológicos existentes. Estos grupos van desde A hasta D, representando el grupo A un potencial de escurrimiento mínimo y el D un potencial de escurrimiento alto. Para asignar a un suelo un grupo determinado se consideran su composición, textura, permeabilidad y las condiciones que controlan su capacidad de infiltración.

\begin{{table}}[H]
\centering
\caption{{Clasificación de grupos hidrológicos del suelo.}}
\label{{tab:hsg_teoria}}
\begin{{tabular}}{{p{{1.4cm}}p{{13.6cm}}}}\toprule
\textbf{{Grupo de suelos}} & \textbf{{Descripción de las características del suelo}} \\\midrule
A & Suelo con bajo potencial de escurrimiento; incluye arenas profundas con muy poco limo y arcilla; también suelo permeable con grava en el perfil. Infiltración básica: 8--12 mm/h. \\
B & Suelos con moderadamente bajo potencial de escurrimiento. Son suelos arenosos menos profundos y más agregados que el grupo A. Este grupo tiene una infiltración mayor que el promedio cuando está húmedo. Ejemplos: suelos migajones, arenosos ligeros y migajones limosos. Infiltración básica: 4--8 mm/h. \\
C & Suelos con moderadamente alto potencial de escurrimiento. Comprende suelos someros y suelos con considerable contenido de arcilla, pero menos que el grupo D. Este grupo tiene una infiltración menor que el promedio después de saturación. Ejemplo: suelos migajones arcillosos. Infiltración básica: 1--4 mm/h. \\
D & Suelos con alto potencial de escurrimiento. Por ejemplo, suelos pesados, con alto contenido de arcillas expandibles y suelos someros con materiales fuertemente cementados. Infiltración básica: menor a 1 mm/h. \\
\bottomrule
\end{{tabular}}
\fuente{{Adaptado de la Resolución 865 de 2004.}}
\end{{table}}

\subsection{{Condición hidrológica}}

El tipo de vegetación y la densidad de la cobertura en la cuenca tienen una gran influencia en la capacidad de infiltración del suelo. A partir de las siguientes categorías se realiza la clasificación de la condición hidrológica.

\begin{{table}}[H]
\centering
\caption{{Condición hidrológica según el uso del suelo.}}
\label{{tab:condicion_hidrologica}}
\begin{{tabular}}{{p{{3cm}}p{{12cm}}}}\toprule
\textbf{{Uso del suelo}} & \textbf{{Condición hidrológica}} \\\midrule
Pastos naturales & Pastos en condiciones malas: dispersos, fuertemente pastoreados, con menos de la mitad del área total con cobertura vegetal. Pastos en condiciones regulares: moderadamente pastoreados, con la mitad o tres cuartas partes del área total con cubierta vegetal. Pastos en buenas condiciones: ligeramente pastoreados y con más de las tres cuartas partes del área total con cubierta vegetal. \\
Áreas boscosas & Áreas en condiciones malas: árboles dispersos y fuertemente pastoreadas, sin crecimiento rastrero. Áreas en condiciones regulares: moderadamente pastoreadas y con algo de crecimiento. Áreas buenas: densamente pobladas y sin pastorear. \\
Pastizales mejorados & Pastizales mezclados con leguminosas sujetas a un cuidadoso sistema de manejo de pastoreo. Son considerados como buenas condiciones hidrológicas. \\
Rotación de praderas & Praderas densas, moderadamente pastoreadas, usadas en una bien planeada rotación de cultivos y praderas; son consideradas como en buenas condiciones hidrológicas. Áreas con material disperso y sobrepastoreado son consideradas como malas condiciones hidrológicas. \\
Cultivos & Condiciones hidrológicas buenas se refieren a cultivos que forman parte de una buena rotación de cultivos, tales como cultivos de escarda, praderas y cultivos tupidos. Condiciones hidrológicas malas se refieren a cultivos manejados basándose en monocultivos. \\
\bottomrule
\end{{tabular}}
\fuente{{Adaptado de la Resolución 865 de 2004.}}
\end{{table}}

\subsection{{Estimación de la Curva Numérica}}

La Curva Numérica se estima luego de clasificar el grupo de suelo, el uso del suelo, el manejo y la condición hidrológica. Para el análisis se adopta la condición promedio de humedad antecedente, correspondiente a $CN_{{II}}$.

\subsection{{Cobertura y uso del suelo}}

Con el fin de caracterizar el comportamiento hidrológico superficial de la cuenca, se realiza la identificación y clasificación de las coberturas y usos del suelo a partir de información cartográfica oficial, empleando la base de datos CORINE Land Cover Colombia 2018 del IDEAM.

A partir de dicha información se obtiene el mapa de coberturas de la tierra correspondiente al área de la cuenca, el cual permite identificar las principales clases de cobertura presentes.

Con base en las coberturas identificadas, estas se reclasifican de acuerdo con la metodología del Servicio de Conservación de Suelos, asignando a cada clase el correspondiente tipo de uso del suelo y su condición hidrológica.

\begin{{table}}[H]
\centering
\caption{{Reclasificación de coberturas y usos del suelo según la metodología SCS.}}
\label{{tab:corine_scs_proyecto}}
\resizebox{{0.98\textwidth}}{{!}}{{%
\begin{{tabular}}{{lll}}\toprule
\textbf{{Cobertura}} & \textbf{{Uso del suelo según SCS}} & \textbf{{Condición hidrológica}} \\\midrule
{cn_landcover_table_tex}
\bottomrule
\end{{tabular}}%
}}
\fuente{{Elaboración propia a partir de CORINE Land Cover Colombia 2018 -- IDEAM y la metodología SCS.}}
\end{{table}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth,height=0.30\textheight,keepaspectratio]{{{corine_fig}}}
\caption{{Mapa de coberturas de la tierra de la cuenca a partir de CORINE Land Cover Colombia 2018.}}
\label{{fig:corine}}
\fuente{{IDEAM, adaptación propia.}}
\end{{figure}}
''' if corine_fig else ''}

\subsection{{Caracterización de suelos y litología}}

La caracterización de los suelos de la cuenca se realiza a partir de la información litológica disponible, la cual se reclasifica en grupos hidrológicos del SCS según su capacidad de infiltración y comportamiento frente a la escorrentía superficial.

\begin{{table}}[H]
\centering
\caption{{Clasificación de tipos de suelo por litología según el método SCS.}}
\label{{tab:litologia_hsg_proyecto}}
\resizebox{{0.96\textwidth}}{{!}}{{%
\begin{{tabular}}{{ll}}\toprule
\textbf{{Litología}} & \textbf{{Tipo de suelo según clasificación CN del SCS}} \\\midrule
{cn_geology_table_tex}
\bottomrule
\end{{tabular}}%
}}
\fuente{{Elaboración propia a partir de información del Servicio Geológico Colombiano y de la clasificación hidrológica del SCS.}}
\end{{table}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth,height=0.30\textheight,keepaspectratio]{{{hsg_fig}}}
\caption{{Distribución litológica y clasificación hidrológica de los suelos de la cuenca.}}
\label{{fig:hsg}}
\fuente{{Elaboración propia a partir del Servicio Geológico Colombiano.}}
\end{{figure}}
''' if hsg_fig else ''}

\subsection{{Determinación del Número de Curva}}

Para cada unidad homogénea de la cuenca se asigna un valor de $CN$ correspondiente a la condición promedio de humedad antecedente ($CN_{{II}}$), considerando la combinación entre el tipo de cobertura del suelo, su condición y el grupo hidrológico del suelo.

Posteriormente se calcula el $CN$ ponderado de la cuenca mediante un promedio ponderado por áreas, utilizando como factores de ponderación el área asociada a cada unidad:

\begin{{equation}}
CN_{{promedio}}=\frac{{\sum CN_iA_i}}{{\sum A_i}}
\end{{equation}}

\begin{{table}}[H]
\centering
\caption{{Cálculo del Número de Curva por unidades homogéneas de la cuenca.}}
\label{{tab:cn}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{llllrrr}}\toprule
\textbf{{Cobertura}} & \textbf{{Uso SCS}} & \textbf{{Condición}} & \textbf{{Grupo HSG}} & \textbf{{CN II}} & \textbf{{Área (km$^2$)}} & \textbf{{$CN_iA_i$}} \\\midrule
{cn_table_tex}
\midrule
\multicolumn{{5}}{{l}}{{\textbf{{Número de Curva ponderado}}}} & \textbf{{{_n(summary.get('area_km2'))}}} & \textbf{{{_n(cn_weighted_report,1)}}} \\
\bottomrule
\end{{tabular}}%
}}
\fuente{{Elaboración propia.}}
\end{{table}}

A partir del procedimiento descrito se obtiene un valor de Número de Curva ponderado igual a \textbf{{{_n(cn_weighted_report,2)}}}, el cual se adopta como parámetro representativo de la cuenca para la estimación de pérdidas en el análisis hidrológico.

La retención potencial máxima y la abstracción inicial se determinan mediante:

\begin{{equation}}
S=\frac{{25400}}{{CN}}-254={_n(cn_data.get('s_retention_mm'),1)}\ \text{{mm}},
\qquad
I_a=0.2S={_n(cn_data.get('ia_abstraction_mm'),1)}\ \text{{mm}}
\end{{equation}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth,height=0.30\textheight,keepaspectratio]{{{cn_fig}}}
\caption{{Distribución espacial del Número de Curva en la cuenca.}}
\label{{fig:cn}}
\fuente{{Elaboración propia.}}
\end{{figure}}
''' if cn_fig else ''}

\section{{Información Meteorológica}}

\subsection{{Estaciones Pluviométricas}}
Para la caracterización hidrometeorológica del área de estudio se consultó el Catálogo Nacional de Estaciones del IDEAM (DHIME). En el Cuadro~\ref{{tab:estaciones_ideam}} y en la Figura~\ref{{fig:estaciones}} se presentan las estaciones seleccionadas en el área de influencia del proyecto.

\begin{{table}}[H]
\centering
\caption{{Estaciones meteorológicas oficiales del IDEAM identificadas en el área de influencia.}}
\label{{tab:estaciones_ideam}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{llllrrrr}}\toprule
\textbf{{Código}} & \textbf{{Nombre}} & \textbf{{Categoría}} & \textbf{{Altitud}} & \textbf{{Latitud}} & \textbf{{Longitud}} & \textbf{{Municipio}} & \textbf{{Dist.}} \\\midrule
{st_table_tex}
\bottomrule
\end{{tabular}}%
}}
\end{{table}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth,height=0.32\textheight,keepaspectratio]{{{st_fig}}}
\caption{{Ubicación espacial de las estaciones meteorológicas del IDEAM en el entorno de la cuenca.}}
\label{{fig:estaciones}}
\end{{figure}}
''' if st_fig else ''}

\section{{Análisis Pluviométrico}}

\subsection{{Polígonos de Thiessen}}

Con base en las estaciones seleccionadas se aplica el método de Polígonos de Thiessen, con el objetivo de determinar el área de influencia de cada estación dentro de la cuenca. La metodología subdivide el área de drenaje en regiones de influencia asociadas a cada estación, permitiendo establecer factores de ponderación espacial para la estimación de la precipitación representativa de la cuenca.

En el Cuadro~\ref{{tab:thiessen}} y la Figura~\ref{{fig:thiessen}} se presenta la distribución de áreas de influencia.

\begin{{table}}[H]
\centering
\caption{{Ponderación espacial de estaciones según Polígonos de Thiessen.}}
\label{{tab:thiessen}}
\begin{{tabular}}{{llrr}}\toprule
\textbf{{Código}} & \textbf{{Estación Meteorológica}} & \textbf{{Área de Influencia (km$^2$)}} & \textbf{{\% Área Cuenca}} \\\midrule
{th_table_tex}
\bottomrule
\end{{tabular}}
\end{{table}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.80\textwidth,height=0.32\textheight,keepaspectratio]{{{thiessen_fig}}}
\caption{{Polígonos de Thiessen y áreas de influencia pluviométrica sobre la cuenca.}}
\label{{fig:thiessen}}
\end{{figure}}
''' if thiessen_fig else ''}

\section{{Curvas Intensidad--Duración--Frecuencia}}

A partir del análisis estadístico de las lluvias máximas anuales se construyen las Curvas Intensidad--Duración--Frecuencia (IDF) para las estaciones pluviométricas representativas, considerando los periodos de retorno de interés. Estas curvas permiten establecer la intensidad de precipitación asociada a diferentes duraciones y frecuencias de ocurrencia y constituyen un insumo fundamental para la construcción de las lluvias de diseño.

La formulación utilizada se expresa como:
\begin{{equation}}
I = \frac{{a \cdot T_r^b}}{{(d + c)^k}}
\end{{equation}}
Donde $I$ es la intensidad de precipitación en mm/h y $d$ es la duración del evento en minutos. En la Figura~\ref{{fig:idf}} se ilustran las familias de curvas generadas.

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.84\textwidth,height=0.32\textheight,keepaspectratio]{{{idf_fig}}}
\caption{{Curvas Intensidad--Duración--Frecuencia (IDF) calculadas para la cuenca.}}
\label{{fig:idf}}
\end{{figure}}
''' if idf_fig else ''}

\section{{Análisis Morfométrico y Caracterización de Subcuencas}}

\subsection{{Subcuencas y Red de Drenaje}}
A partir de los puntos de confluencia y umbrales de acumulación se subdividió la cuenca en \textbf{{{summary.get('subbasin_count','N/D')}}} subcuencas tributarias. En las Figuras~\ref{{fig:watershed_drenaje}} y~\ref{{fig:subcuencas}} y en el Cuadro~\ref{{tab:subcuencas}} se detalla la partición territorial.

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.82\textwidth,height=0.32\textheight,keepaspectratio]{{{watershed_fig}}}
\caption{{Cuenca delimitada, red de drenaje y cauce principal.}}
\label{{fig:watershed_drenaje}}
\end{{figure}}
''' if watershed_fig else ''}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.80\textwidth,height=0.32\textheight,keepaspectratio]{{{subfig}}}
\caption{{Subdivisión en subcuencas hidrológicas dentro de la cuenca principal.}}
\label{{fig:subcuencas}}
\end{{figure}}
''' if subfig else ''}

\begin{{table}}[H]
\centering
\caption{{Distribución de áreas por subcuencas hidrológicas principales.}}
\label{{tab:subcuencas}}
\begin{{tabular}}{{rrr}}\toprule
\textbf{{ID Subcuenca}} & \textbf{{Área (km$^2$)}} & \textbf{{\% Área Total}} \\\midrule
{sub_rows}
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Características del Cauce Principal y Perfil Longitudinal}}
En el Cuadro~\ref{{tab:cauce}} se resumen las características geométricas y altimétricas del cauce principal, complementadas con su perfil longitudinal en la Figura~\ref{{fig:perfil}}.

\begin{{table}}[H]
\centering
\caption{{Características geométricas y altimétricas del cauce principal.}}
\label{{tab:cauce}}
\begin{{tabular}}{{p{{8.5cm}}r}}\toprule
\textbf{{Parámetro del Cauce}} & \textbf{{Valor}} \\\midrule
Longitud del Cauce Principal ($L$) & \textbf{{{_n(summary.get('main_channel_length_km'))} km}} \\
Elevación en Cabecera & {_n(summary.get('main_channel_elevation_source_m'))} msnm \\
Elevación en Exutorio & {_n(summary.get('main_channel_elevation_outlet_m'))} msnm \\
Desnivel Topográfico ($\Delta H$) & {_n(desnivel)} m \\
Pendiente Media del Cauce ($S$) & {_n(summary.get('main_channel_slope_percent'),3)}\% \\
\bottomrule
\end{{tabular}}
\end{{table}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.88\textwidth,height=0.32\textheight,keepaspectratio]{{{profile}}}
\caption{{Perfil longitudinal altimétrico del cauce principal.}}
\label{{fig:perfil}}
\end{{figure}}
''' if profile else ''}

\subsection{{Cartografía Complementaria de Subcuencas y Red de Drenaje}}
La cartografía generada constituye la base geométrica para la formulación de los modelos de escorrentía superficial, delimitación de zonas de recarga y dimensionamiento de la red de colectores e infraestructuras de paso.

% ============================== 6. CARACTERIZACIÓN HIDROLÓGICA ==============================
\section{{Modelación Hidrológica y Caudales Máximos}}
La transformación de lluvia en escorrentía se efectuó aplicando el modelo del Hidrograma Unitario del SCS conjuntamente con el Método Racional. En el Cuadro~\ref{{tab:caudales}} se consolidan los caudales pico estimados para cada periodo de retorno, y en la Figura~\ref{{fig:hidrogramas}} se grafican los hidrogramas temporales de diseño $Q(t)$.

\begin{{table}}[H]
\centering
\caption{{Resumen de caudales pico obtenidos para diferentes periodos de retorno.}}
\label{{tab:caudales}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{lrrrrrr}}\toprule
\textbf{{Periodo Retorno}} & \textbf{{$I_{{diseno}}$ (mm/h)}} & \textbf{{$P_{{total}}$ (mm)}} & \textbf{{$P_{{efectiva}}$ (mm)}} & \textbf{{$Q_{{Racional}}$ (m$^3$/s)}} & \textbf{{$Q_{{SCS}}$ (m$^3$/s)}} & \textbf{{$Q_{{Diseno}}$ (m$^3$/s)}} \\\midrule
{q_table_tex}
\bottomrule
\end{{tabular}}%
}}
\end{{table}}

{rf'''
\begin{{figure}}[H]
\centering
\includegraphics[width=0.84\textwidth,height=0.32\textheight,keepaspectratio]{{{hydro_fig}}}
\caption{{Hidrogramas de caudal de diseño para diferentes periodos de retorno.}}
\label{{fig:hidrogramas}}
\end{{figure}}
''' if hydro_fig else ''}

% ============================== 7. ANÁLISIS INTEGRADO ==============================
\section{{Análisis Integrado de Resultados}}
La integración morfométrica e hidrológica evidencia una cuenca con factor de forma $K_f = {_n(summary.get('factor_forma'), 3)}$ e índice de compacidad $K_c = {_n(summary.get('coeficiente_compacidad'), 3)}$, lo que se traduce en hidrogramas con tiempos al pico moderados y respuesta hidrodinámica amortiguada. Para el periodo de retorno de diseño $T_r = 100$ años, el caudal pico estimado de \textbf{{{_n(peak_flows[5]['caudal_diseno_m3_s'] if len(peak_flows)>5 else 0)} m$^3$/s}} representa la condición de solicitación extrema recomendada para el diseño de obras de protección hidráulica y pasos vehiculares.

% ============================== 8. CONCLUSIONES ==============================
\section{{Conclusiones y Recomendaciones}}
\begin{{itemize}}
\item Se delimitó exitosamente la cuenca aportante para \textbf{{{_esc(site)}}}, abarcando un área total de \textbf{{{_n(summary.get('area_km2'))} km$^2$}} y un perímetro de \textbf{{{_n(summary.get('perimetro_km'))} km}}.
\item La respuesta temporal del sistema arrojó un tiempo de concentración medio adoptado de \textbf{{{_n(tc_avg_min, 1)} minutos}} ({_n(tc_avg_h, 2)} h), fundamentado en el análisis comparativo de cinco formulaciones hidrológicas.
\item El Número de Curva ponderado estimado ($CN = {_n(summary.get('cn_weighted'), 1)}$) representa adecuadamente las coberturas de pastos, vegetación y suelos de la cuenca.
\item Los caudales máximos de diseño modelados para los periodos de retorno de 25, 50 y 100 años corresponden a \textbf{{{_n(peak_flows[3]['caudal_diseno_m3_s'] if len(peak_flows)>3 else 0)} m$^3$/s}}, \textbf{{{_n(peak_flows[4]['caudal_diseno_m3_s'] if len(peak_flows)>4 else 0)} m$^3$/s}} y \textbf{{{_n(peak_flows[5]['caudal_diseno_m3_s'] if len(peak_flows)>5 else 0)} m$^3$/s}} respectivamente.
\item Se recomienda implementar estructuras de disipación de energía y considerar los hidrogramas generados para el análisis de tránsito de avenidas.
\end{{itemize}}

% ============================== 9. LIMITACIONES ==============================
\section{{Limitaciones Técnicas}}
Los resultados se derivan del procesamiento de información topográfica, hidrometeorológica y cartográfica disponible, junto con metodologías hidrológicas de uso técnico. El presente estudio no reemplaza levantamientos batimétricos directos en el cauce ni la verificación estructural en campo de las obras de paso existentes.

% ============================== 10. ANEXOS IDEAM ==============================
\newpage
\section{{Anexos IDEAM -- Registro y Tratamiento de Información Pluviométrica}}
En este anexo se consolida el registro completo de las estaciones meteorológicas del IDEAM identificadas en el entorno territorial del proyecto, junto con las metodologías técnicas adoptadas para la verificación de consistencia, homogeneización y completación de series climáticas.

\subsection*{{Catálogo y Variables Reales de Estaciones IDEAM}}
En el Cuadro~\ref{{tab:anexo_ideam}} se presentan los datos reales extraídos del Catálogo Nacional de Estaciones del IDEAM (DHIME):

\begin{{table}}[H]
\centering
\caption{{Registro oficial de estaciones meteorológicas del IDEAM consultadas por HydroBasin.}}
\label{{tab:anexo_ideam}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{lllcccccr}}\toprule
\textbf{{Código}} & \textbf{{Nombre}} & \textbf{{Categoría}} & \textbf{{Altitud}} & \textbf{{Latitud}} & \textbf{{Longitud}} & \textbf{{Municipio}} & \textbf{{Distancia}} & \textbf{{Estado}} \\\midrule
{anexo_ideam_tex}
\bottomrule
\end{{tabular}}%
}}
\end{{table}}

\subsection*{{Metodología de Completación y Homogeneización de Datos}}
Para el tratamiento de vacíos de información o registros faltantes en las series pluviométricas se aplican los criterios técnicos estandarizados por el IDEAM y la Organización Meteorológica Mundial (OMM No. 168):

\begin{{enumerate}}
\item \textbf{{Método de Proporciones Normales (Normal Ratio Method):}} Aplicado cuando la precipitación media anual de las estaciones vecinas difiere en más de un 10\% respecto a la estación de interés:
\begin{{equation}}
P_x = \frac{{1}}{{n}} \sum_{{i=1}}^{{n}} \left( \frac{{N_x}}{{N_i}} \right) P_i
\end{{equation}}
Donde $P_x$ es la precipitación estimada para la estación faltante, $N_x$ es su precipitación media anual normal, $N_i$ es la precipitación media anual de la estación vecina $i$, y $P_i$ es la precipitación observada en el periodo correspondiente.

\item \textbf{{Regresión Lineal y Correlación Cruzada:}} Utilizada para estaciones con coeficientes de correlación $R^2 \ge 0.75$ y regímenes pluviométricos climatológicamente análogos.

\item \textbf{{Interpolación Espacial por Distancia Inversa Ponderada (IDW):}} Empleada para construir campos continuos de precipitación a partir de la red pluviométrica circundante:
\begin{{equation}}
P(x, y) = \frac{{\sum_{{i=1}}^{{n}} \frac{{P_i}}{{d_i^p}}}}{{\sum_{{i=1}}^{{n}} \frac{{1}}{{d_i^p}}}}
\end{{equation}}
Donde $d_i$ es la distancia geodésica a la estación $i$ y $p=2$ es el exponente de ponderación adoptado.
\end{{enumerate}}

\end{{document}}
"""


def _find_tectonic() -> str | None:
    import sys
    found = shutil.which("tectonic") or shutil.which("tectonic.exe") or shutil.which("tecto") or shutil.which("tecto.exe")
    if found:
        return found
    py_dir = Path(sys.executable).parent
    for candidate in ("tectonic.exe", "tectonic", "tecto.exe", "tecto"):
        p = py_dir / candidate
        if p.exists():
            return str(p)
    for root in (Path.cwd(), Path(__file__).resolve().parents[2]):
        for candidate in ("backend/.venv/Scripts/tectonic.exe", "backend/.venv/Scripts/tecto.exe", ".venv/Scripts/tectonic.exe"):
            p = (root / candidate).resolve()
            if p.exists():
                return str(p)
    return None


def _find_pandoc() -> str | None:
    import sys
    found = shutil.which("pandoc") or shutil.which("pandoc.exe")
    if found:
        return found
    py_dir = Path(sys.executable).parent
    for candidate in ("pandoc.exe", "pandoc"):
        p = py_dir / candidate
        if p.exists():
            return str(p)
    for root in (Path.cwd(), Path(__file__).resolve().parents[2]):
        for candidate in ("backend/.venv/Scripts/pandoc.exe", ".venv/Scripts/pandoc.exe"):
            p = (root / candidate).resolve()
            if p.exists():
                return str(p)
    return None


def _compile_report(tex: Path, output_dir: Path):
    compiler = _find_tectonic()
    if not compiler:
        return None, "Tectonic no está disponible en PATH."
    out = output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [compiler, tex.name, "--outdir", str(out)],
            cwd=str(tex.parent.resolve()),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    pdf = out / f"{tex.stem}.pdf"
    if proc.returncode != 0 or not pdf.exists():
        return None, (proc.stderr or proc.stdout or "Error desconocido")[-2200:]
    return pdf, None


def _convert_with_pandoc(tex: Path, output_docx: Path) -> bool:
    pandoc = _find_pandoc()
    if not pandoc:
        return False
    try:
        proc = subprocess.run(
            [pandoc, str(tex), "-o", str(output_docx)],
            cwd=str(tex.parent.resolve()),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode == 0 and output_docx.exists()
    except Exception:
        return False


def generar_informes(
    output_dir: Path,
    summary: dict,
    figures: dict[str, str],
    subbasins=None,
    main_channel=None,
    watershed=None,
    drainage=None,
) -> dict:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outlet = summary.get("outlet_original") or {}
    loc = resolve_administrative_location(float(outlet.get("y", 0)), float(outlet.get("x", 0)))
    summary.update(loc)
    summary["location_label"] = location_label(loc)
    summary["site_name"] = _site(summary, loc)

    # 1. Mapa satelital para el informe
    sat = _satellite_map(output_dir, summary, loc)
    if sat:
        figures["location_satellite"] = sat

    # 2. Generación del Informe Técnico PDF (LaTeX + Tectonic)
    report_tex = output_dir / "informe_hydrobasin.tex"
    report_tex.write_text(_report(output_dir, summary, figures, subbasins, loc), encoding="utf-8")
    report_pdf, report_err = _compile_report(report_tex, output_dir)

    # 3. Generación del Informe Técnico en Word (.docx) directamente desde LaTeX mediante Pandoc
    docx_path = output_dir / "informe_hydrobasin.docx"
    pandoc_ok = convert_latex_to_docx(report_tex, docx_path)
    if not pandoc_ok or not docx_path.exists():
        try:
            generar_informe_docx(docx_path, summary, figures, subbasins, loc)
        except Exception:
            docx_path = None

    # 4. Generación del Plano Hidrográfico PDF A3 (Matplotlib Vectorial Puro, exactamente 2 páginas)
    plan_pdf_path = output_dir / "plano_hidrografico.pdf"
    try:
        generar_plano_pdf(
            plan_pdf_path,
            summary,
            watershed,
            drainage,
            subbasins,
            main_channel,
            loc,
        )
        plan_err = None
    except Exception as exc:
        plan_err = str(exc)

    # 5. Exportación a Excel (.xlsx) de Estaciones IDEAM, Thiessen, IDF y Caudales
    excel_path = output_dir / "estaciones_ideam.xlsx"
    try:
        export_ideam_and_hydrology_excel(excel_path, summary)
    except Exception:
        excel_path = None

    errors = [e for e in (report_err, plan_err) if e]

    return {
        "tex": report_tex.name,
        "pdf": report_pdf.name if report_pdf else None,
        "docx": docx_path.name if docx_path and docx_path.exists() else None,
        "excel": excel_path.name if excel_path and excel_path.exists() else None,
        "plan_tex": None,
        "plan_pdf": plan_pdf_path.name if plan_pdf_path.exists() else None,
        "compiled": bool(report_pdf and plan_pdf_path.exists()),
        "compiler_found": bool(_find_tectonic()),
        "compile_error": " | ".join(errors) if errors else None,
    }
