from __future__ import annotations

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

from .location import location_label, resolve_administrative_location


def _n(value, digits=2):
    return "N/D" if value is None else f"{value:.{digits}f}"


def _latex_escape(value) -> str:
    text = str(value or "")
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _tc_minutes(summary: dict, key: str):
    value = summary.get(key)
    return None if value is None else float(value) * 60.0


def _site_name(summary: dict, location: dict) -> str:
    project = str(summary.get("project_name") or "").strip()
    if project and project.lower() not in {"cuenca sin título", "cuenca sin titulo"}:
        return project
    if location.get("country_code") == "COL" and location.get("municipality"):
        return f"Cuenca aportante - {location['municipality']}, {location.get('department') or 'Colombia'}"
    if location.get("country"):
        return f"Cuenca aportante - {location['country']}"
    return "Cuenca aportante al exutorio seleccionado"


def _satellite_location_figure(output_dir: Path, summary: dict, location: dict) -> str | None:
    outlet = summary.get("outlet_original") or {}
    lat = outlet.get("y")
    lon = outlet.get("x")
    if lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)
    dlat = 0.055
    dlng = 0.055 / max(0.25, abs(__import__('math').cos(__import__('math').radians(lat))))
    bbox = f"{lon-dlng},{lat-dlat},{lon+dlng},{lat+dlat}"
    params = urlencode({
        "bbox": bbox,
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "1400,850",
        "format": "png32",
        "transparent": "false",
        "f": "image",
    })
    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?{params}"
    try:
        request = Request(url, headers={"User-Agent": "HydroBasin/1.0"})
        with urlopen(request, timeout=25) as response:
            image_bytes = response.read()
        image = plt.imread(BytesIO(image_bytes), format="png")
        fig, ax = plt.subplots(figsize=(11.5, 6.5))
        ax.imshow(image, extent=[lon-dlng, lon+dlng, lat-dlat, lat+dlat])
        ax.scatter([lon], [lat], s=125, marker="o", facecolor="#ef4444", edgecolor="white", linewidth=2.0, zorder=4)
        ax.annotate("Exutorio", (lon, lat), xytext=(10, 10), textcoords="offset points", color="white",
                    fontsize=10, fontweight="bold", bbox={"boxstyle": "round,pad=0.25", "fc": "#111827", "alpha": 0.78, "ec": "none"})
        ax.set_title(f"Localización satelital - {location_label(location)}", fontsize=12, fontweight="bold")
        ax.set_xlabel("Longitud")
        ax.set_ylabel("Latitud")
        ax.grid(True, alpha=0.18)
        path = output_dir / "figuras" / "00_ubicacion_satelital.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return "figuras/00_ubicacion_satelital.png"
    except Exception:
        return None


def _subbasin_rows(subbasins, limit: int = 20) -> str:
    if subbasins is None or subbasins.empty or "area_km2" not in subbasins.columns:
        return ""
    top = subbasins.sort_values("area_km2", ascending=False).head(limit)
    return "\n".join(f"{int(row['subbasin_id'])} & {_n(float(row['area_km2']), 2)} \\\\" for _, row in top.iterrows())


def _location_table(summary: dict, location: dict) -> str:
    outlet = summary.get("outlet_original") or {}
    snapped = summary.get("outlet_snapped") or {}
    if location.get("country_code") == "COL":
        admin = f"{location.get('municipality') or 'N/D'}, {location.get('department') or 'N/D'}, {location.get('country') or 'Colombia'}"
    else:
        admin = location.get("country") or "N/D"
    return rf"""
\begin{{tabular}}{{p{{4.7cm}}p{{10.2cm}}}}
\toprule
\textbf{{Dato}} & \textbf{{Información}} \\
\midrule
Ubicación administrativa & {_latex_escape(admin)} \\
Coordenadas del exutorio & {_n(outlet.get('y'), 6)}, {_n(outlet.get('x'), 6)} ({_latex_escape(outlet.get('crs') or 'EPSG:4326')}) \\
Exutorio ajustado & {_n(snapped.get('y'), 6)}, {_n(snapped.get('x'), 6)} ({_latex_escape(snapped.get('crs') or summary.get('crs_dem') or 'N/D')}) \\
Fuente del DEM & {_latex_escape(summary.get('dem_source') or 'N/D')} \\
CRS del DEM & {_latex_escape(summary.get('crs_dem') or 'N/D')} \\
CRS de cálculo & {_latex_escape(summary.get('crs_calculo') or 'N/D')} \\
Resolución aproximada & {_latex_escape(' x '.join(f'{v:.1f}' for v in (summary.get('metric_resolution_m') or [])) + ' m' if summary.get('metric_resolution_m') else 'N/D')} \\
Área delimitada & {_n(summary.get('area_km2'))} km$^2$ \\
\bottomrule
\end{{tabular}}
"""


def _report_tex(summary: dict, figures: dict[str, str], subbasins, location: dict) -> str:
    site = _site_name(summary, location)
    loc_label = location_label(location)
    satellite = figures.get("location_satellite")
    subrows = _subbasin_rows(subbasins)
    tc_k = _tc_minutes(summary, "tc_kirpich_h")
    tc_t = _tc_minutes(summary, "tc_temez_h")
    tc_p = _tc_minutes(summary, "tc_promedio_h")

    location_figure = rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{{satellite}}}
\caption{{Localización satelital del punto de análisis. Fuente cartográfica: Esri World Imagery.}}
\end{{figure}}
""" if satellite else ""

    sub_section = ""
    if subrows:
        sub_section = rf"""
\section{{Subcuencas}}
La subdivisión hidrológica identificó \textbf{{{summary.get('subbasin_count', 0)}}} unidades internas. Estas subcuencas permiten reconocer la organización espacial de los aportes y facilitan la lectura de la conectividad de la red hacia el cauce principal. La tabla presenta las unidades de mayor extensión, mientras que la cartografía muestra su distribución completa dentro de la cuenca.

\begin{{center}}
\begin{{tabular}}{{rr}}
\toprule
\textbf{{ID}} & \textbf{{Área (km$^2$)}} \\
\midrule
{subrows}
\bottomrule
\end{{tabular}}
\end{{center}}

\begin{{figure}}[H]
\centering\includegraphics[width=0.91\textwidth]{{{figures.get('subbasins','')}}}
\caption{{Subcuencas hidrológicas, red de drenaje y cauce principal.}}
\end{{figure}}
"""

    profile = ""
    if figures.get("profile"):
        profile = rf"""
\begin{{figure}}[H]
\centering\includegraphics[width=0.93\textwidth]{{{figures['profile']}}}
\caption{{Perfil longitudinal del cauce principal.}}
\end{{figure}}
"""

    intro = f"El presente informe técnico corresponde al análisis de la {site}, localizada en {loc_label}. El estudio parte de un Modelo Digital de Elevación (DEM) y del punto de salida seleccionado, con el propósito de representar de manera reproducible la cuenca aportante y su estructura de drenaje. A partir de la topografía se obtienen la divisoria de aguas, la red hidrográfica, la jerarquía de corrientes, las subcuencas internas, el cauce principal y los parámetros morfométricos que permiten describir la configuración física del sistema."
    scope = f"El alcance comprende la delimitación automática de la {site}, el acondicionamiento hidrológico del DEM, el cálculo de dirección y acumulación de flujo, el ajuste del exutorio, la extracción y jerarquización de la red de drenaje, la subdivisión en subcuencas, la identificación del cauce principal y su perfil longitudinal, y el cálculo de indicadores geométricos e hidrológicos derivados del terreno. Los resultados constituyen un insumo técnico de caracterización y no sustituyen la validación con cartografía oficial, información de campo o registros hidrometeorológicos cuando el análisis se utilice para diseño."
    objective = f"Delimitar y caracterizar la {site}, ubicada en {loc_label}, mediante el procesamiento de un Modelo Digital de Elevación y la evaluación de su estructura de drenaje, con el fin de obtener parámetros morfométricos, hidrológicos y cartográficos útiles para la comprensión del comportamiento físico de la cuenca."

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{xcolor}}
\usepackage{{fancyhdr}}
\usepackage{{array}}
\usepackage{{longtable}}
\geometry{{margin=2.25cm}}
\definecolor{{hb}}{{HTML}}{{176B73}}
\definecolor{{hbsoft}}{{HTML}}{{EDF5F5}}
\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{HydroBasin}}
\rhead{{Informe de análisis de cuenca}}
\cfoot{{\thepage}}
\begin{{document}}

\begin{{titlepage}}
\vspace*{{1.5cm}}
{{\color{{hb}}\Large\bfseries HYDROBASIN / WATERSHED STUDIO}}\\[0.55cm]
{{\Huge\bfseries Informe de delimitación y análisis de cuenca hidrográfica}}\\[0.45cm]
{{\Large {_latex_escape(site)}}}\\[1.2cm]
{_location_table(summary, location)}
\vfill
{{\small Documento técnico generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}.}}
\end{{titlepage}}

\tableofcontents
\newpage

\section{{Introducción}}
{_latex_escape(intro)}

\section{{Alcance}}
{_latex_escape(scope)}

\section{{Objetivos}}
\subsection*{{Objetivo general}}
{_latex_escape(objective)}

\subsection*{{Objetivos específicos}}
\begin{{itemize}}
\item Acondicionar hidrológicamente el DEM asociado a {_latex_escape(site)} conservando su resolución de análisis.
\item Determinar la dirección y acumulación de flujo y delimitar la cuenca aportante al exutorio seleccionado.
\item Extraer y jerarquizar la red de drenaje mediante el orden de Strahler e identificar las subcuencas internas.
\item Determinar el cauce principal, su longitud, pendiente, desnivel y perfil longitudinal.
\item Calcular parámetros morfométricos e hidrológicos y generar cartografía técnica para {_latex_escape(loc_label)}.
\end{{itemize}}

\section{{Ubicación}}
La zona analizada se localiza en \textbf{{{_latex_escape(loc_label)}}}. El punto seleccionado como exutorio se encuentra en las coordenadas \textbf{{{_n((summary.get('outlet_original') or {{}}).get('y'),6)}, {_n((summary.get('outlet_original') or {{}}).get('x'),6)}}} en EPSG:4326. La identificación administrativa se obtiene mediante consulta espacial a capas de ArcGIS; para Colombia se determina municipio y departamento, mientras que para ubicaciones internacionales se conserva el país como referencia administrativa principal.

{location_figure}

\section{{Datos de entrada y referencia espacial}}
{_location_table(summary, location)}

\section{{Metodología}}
El procesamiento de {_latex_escape(site)} inicia con la lectura y validación del Modelo Digital de Elevación, verificando su sistema de referencia, resolución y cobertura. Posteriormente se realiza el acondicionamiento hidrológico de la superficie mediante corrección de depresiones, pits y zonas planas, de forma que el terreno represente una superficie continua para el tránsito del flujo sin reducir la resolución espacial utilizada en el análisis.

Sobre el DEM acondicionado se calcula la dirección de flujo mediante el esquema D8 y, a partir de ella, la acumulación de flujo para cada celda. El punto suministrado por el usuario se ajusta a una celda con acumulación significativa, evitando que pequeñas diferencias de posicionamiento desplacen artificialmente el exutorio fuera de la red derivada. Desde este punto se delimita la cuenca aportante y se vectoriza su divisoria de aguas.

La red de drenaje se extrae utilizando un área mínima de aporte de {_n(summary.get('minimum_area_km2'),3)} km$^2$, equivalente aproximadamente a {_n(summary.get('drainage_threshold'),0)} celdas. Los segmentos resultantes se jerarquizan mediante el orden de Strahler y la estructura D8 se utiliza para subdividir la cuenca en unidades hidrológicas internas. Finalmente, el cauce principal se traza desde el exutorio hacia la cabecera siguiendo la conectividad aguas arriba de mayor acumulación; con su longitud, elevaciones y desnivel se obtiene la pendiente media y se estiman tiempos de concentración mediante expresiones empíricas de Kirpich y Témez.

\section{{Resultados hidrológicos y morfométricos}}
\begin{{center}}
\begin{{tabular}}{{p{{8.2cm}}r}}
\toprule
\textbf{{Parámetro}} & \textbf{{Resultado}} \\
\midrule
Área & {_n(summary.get('area_km2'))} km$^2$ \\
Perímetro & {_n(summary.get('perimetro_km'))} km \\
Longitud axial & {_n(summary.get('longitud_axial_km'))} km \\
Factor de forma & {_n(summary.get('factor_forma'),3)} \\
Compacidad de Gravelius & {_n(summary.get('coeficiente_compacidad'),3)} \\
Relación de circularidad & {_n(summary.get('relacion_circularidad'),3)} \\
Densidad de drenaje & {_n(summary.get('densidad_drenaje_km_km2'),3)} km/km$^2$ \\
Orden máximo de Strahler & {summary.get('strahler_max','N/D')} \\
Número de subcuencas & {summary.get('subbasin_count','N/D')} \\
Elevación mínima & {_n(summary.get('elevacion_min_m'))} m \\
Elevación máxima & {_n(summary.get('elevacion_max_m'))} m \\
Elevación media & {_n(summary.get('elevacion_media_m'))} m \\
Relieve total & {_n(summary.get('relieve_cuenca_m'))} m \\
\bottomrule
\end{{tabular}}
\end{{center}}

\section{{Cauce principal y tiempo de concentración}}
El cauce principal constituye la trayectoria de drenaje dominante dentro de la cuenca. Para {_latex_escape(site)} se obtuvo una longitud aproximada de \textbf{{{_n(summary.get('main_channel_length_km'))} km}}, desde la cabecera identificada por conectividad D8 hasta el exutorio ajustado. El perfil longitudinal permite observar la variación de elevación a lo largo de esta trayectoria y constituye una referencia directa para interpretar el gradiente general de evacuación del flujo.

\begin{{center}}
\begin{{tabular}}{{p{{8.4cm}}r}}
\toprule
\textbf{{Parámetro}} & \textbf{{Resultado}} \\
\midrule
Longitud del cauce principal & {_n(summary.get('main_channel_length_km'))} km \\
Elevación en cabecera & {_n(summary.get('main_channel_elevation_source_m'))} m \\
Elevación en exutorio & {_n(summary.get('main_channel_elevation_outlet_m'))} m \\
Desnivel & {_n((summary.get('main_channel_elevation_source_m') or 0)-(summary.get('main_channel_elevation_outlet_m') or 0))} m \\
Pendiente media & {_n(summary.get('main_channel_slope_percent'),3)} \% \\
Tiempo de concentración Kirpich & {_n(tc_k)} min \\
Tiempo de concentración Témez & {_n(tc_t)} min \\
Tiempo de concentración promedio & {_n(tc_p)} min \\
\bottomrule
\end{{tabular}}
\end{{center}}
{profile}

{sub_section}

\section{{Cartografía técnica}}
La cartografía se selecciona para mostrar resultados complementarios y evitar repetir figuras con la misma información. Se presentan el contexto del DEM, la acumulación de flujo, la cuenca con su red y cauce principal, y la jerarquía de Strahler. El mapa de subcuencas y el perfil longitudinal se presentan en sus respectivas secciones temáticas.

\begin{{figure}}[H]\centering\includegraphics[width=0.91\textwidth]{{{figures.get('dem','')}}}\caption{{Contexto del Modelo Digital de Elevación y cuenca delimitada.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.91\textwidth]{{{figures.get('accumulation','')}}}\caption{{Acumulación de flujo dentro de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.91\textwidth]{{{figures.get('watershed','')}}}\caption{{Cuenca principal, red de drenaje y cauce principal.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=0.91\textwidth]{{{figures.get('strahler','')}}}\caption{{Jerarquía de corrientes según el orden de Strahler.}}\end{{figure}}

\section{{Análisis e interpretación}}
La geometría de la cuenca se interpreta conjuntamente mediante el factor de forma, la compacidad y la relación de circularidad. Para {_latex_escape(site)}, el factor de forma es {_n(summary.get('factor_forma'),3)} y el índice de compacidad de Gravelius es {_n(summary.get('coeficiente_compacidad'),3)}, por lo que la respuesta hidrológica no debe asociarse únicamente al área sino también a la distribución espacial de las distancias de recorrido hacia el exutorio. La densidad de drenaje obtenida, {_n(summary.get('densidad_drenaje_km_km2'),3)} km/km$^2$, está condicionada por el umbral de extracción seleccionado y debe interpretarse como una representación derivada del DEM, no como un inventario de cauces verificado en campo.

El cauce principal presenta una pendiente media de {_n(summary.get('main_channel_slope_percent'),2)}\% y un desnivel aproximado de {_n((summary.get('main_channel_elevation_source_m') or 0)-(summary.get('main_channel_elevation_outlet_m') or 0))} m. La combinación entre relieve, longitud del cauce y organización interna de las subcuencas controla los recorridos principales del flujo hacia el punto de salida. Los tiempos de concentración calculados son estimaciones empíricas y constituyen valores de referencia que deben contrastarse con criterios y datos propios del proyecto cuando se empleen en modelación o diseño hidráulico.

\section{{Conclusiones}}
La delimitación automática permitió establecer la cuenca aportante asociada a {_latex_escape(site)} y generar una representación integrada de su divisoria, red de drenaje, subcuencas y cauce principal. Los resultados proporcionan una base espacial reproducible para análisis posteriores y permiten identificar las principales características geométricas y topográficas del sistema.

La ubicación administrativa y las coordenadas del exutorio quedan incorporadas como parte de la trazabilidad del análisis. La cartografía y los archivos GIS generados pueden utilizarse como insumo para revisión técnica, integración en SIG y preparación de análisis hidrológicos de mayor detalle.

\section{{Limitaciones}}
Los resultados dependen de la resolución y calidad del DEM, del acondicionamiento hidrológico, de la posición del exutorio y del área mínima de aporte utilizada para representar la red. HydroBasin no infiere precipitación, temperatura, caudales observados ni condiciones de cobertura o suelo a partir del DEM. La identificación administrativa proviene de capas públicas de ArcGIS y debe verificarse cuando la ubicación se encuentre sobre límites territoriales.

\end{{document}}
"""


def _title_block(summary: dict, location: dict, sheet: int, title: str) -> str:
    outlet = summary.get("outlet_original") or {}
    site = _site_name(summary, location)
    return rf"""
\vspace{{1.5mm}}
\begin{{tabular}}{{|p{{3.1cm}}|p{{6.0cm}}|p{{3.2cm}}|p{{4.4cm}}|p{{3.0cm}}|}}
\hline
\textbf{{PROYECTO}} & \multicolumn{{4}}{{l|}}{{{_latex_escape(site)}}} \\
\hline
\textbf{{PLANO}} & \multicolumn{{2}}{{l|}}{{{_latex_escape(title)}}} & \textbf{{HOJA}} & {sheet} de 2 \\
\hline
\textbf{{UBICACIÓN}} & \multicolumn{{2}}{{l|}}{{{_latex_escape(location_label(location))}}} & \textbf{{FECHA}} & {datetime.now().strftime('%d/%m/%Y')} \\
\hline
\textbf{{EXUTORIO}} & \multicolumn{{2}}{{l|}}{{{_n(outlet.get('y'),6)}, {_n(outlet.get('x'),6)}}} & \textbf{{CRS}} & {_latex_escape(summary.get('crs_calculo') or 'N/D')} \\
\hline
\textbf{{DEM}} & \multicolumn{{2}}{{l|}}{{{_latex_escape(summary.get('dem_source') or 'N/D')}}} & \textbf{{ÁREA}} & {_n(summary.get('area_km2'))} km$^2$ \\
\hline
\multicolumn{{3}}{{|l|}}{{HydroBasin / Watershed Studio}} & \textbf{{VERSIÓN}} & 1.0 \\
\hline
\end{{tabular}}
"""


def _plan_tex(summary: dict, figures: dict[str, str], location: dict) -> str:
    profile = figures.get("profile")
    subbasins = figures.get("subbasins")
    second_main = subbasins or figures.get("watershed")
    tc_k = _tc_minutes(summary, "tc_kirpich_h")
    return rf"""\documentclass[9pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage[a3paper,landscape,margin=8mm]{{geometry}}
\usepackage{{graphicx}}
\usepackage{{array}}
\usepackage{{booktabs}}
\usepackage{{float}}
\pagestyle{{empty}}
\begin{{document}}

\begin{{center}}{{\LARGE\bfseries PLANO HIDROGRÁFICO - DELIMITACIÓN GENERAL Y RED DE DRENAJE}}\end{{center}}
\begin{{minipage}}[t]{{0.79\textwidth}}
\centering\includegraphics[width=\linewidth,height=0.72\textheight,keepaspectratio]{{{figures.get('plan','')}}}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.19\textwidth}}
\small\textbf{{CUADRO TÉCNICO}}\\[1mm]
\begin{{tabular}}{{@{{}}lr@{{}}}}
Área & {_n(summary.get('area_km2'))} km$^2$\\
Perímetro & {_n(summary.get('perimetro_km'))} km\\
Compacidad & {_n(summary.get('coeficiente_compacidad'),3)}\\
Circularidad & {_n(summary.get('relacion_circularidad'),3)}\\
Dens. drenaje & {_n(summary.get('densidad_drenaje_km_km2'),3)}\\
Strahler máx. & {summary.get('strahler_max','N/D')}\\
Subcuencas & {summary.get('subbasin_count','N/D')}\\
Cauce principal & {_n(summary.get('main_channel_length_km'))} km\\
Pendiente & {_n(summary.get('main_channel_slope_percent'),2)}\%\\
Tc Kirpich & {_n(tc_k)} min\\
\end{{tabular}}
\end{{minipage}}
{_title_block(summary, location, 1, 'Delimitación general, subcuencas, drenajes y cauce principal')}

\newpage
\begin{{center}}{{\LARGE\bfseries PLANO HIDROGRÁFICO - SUBCUENCAS Y PERFIL DEL CAUCE PRINCIPAL}}\end{{center}}
\begin{{minipage}}[t]{{0.60\textwidth}}
\centering\includegraphics[width=\linewidth,height=0.63\textheight,keepaspectratio]{{{second_main}}}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.38\textwidth}}
\textbf{{CAUCE PRINCIPAL}}\\[1.5mm]
Longitud: {_n(summary.get('main_channel_length_km'))} km\\
Elevación cabecera: {_n(summary.get('main_channel_elevation_source_m'))} m\\
Elevación exutorio: {_n(summary.get('main_channel_elevation_outlet_m'))} m\\
Pendiente media: {_n(summary.get('main_channel_slope_percent'),3)}\%\\
Tc Kirpich: {_n(tc_k)} min\\[3mm]
\textbf{{PERFIL LONGITUDINAL}}\\[1mm]
{rf'\includegraphics[width=\linewidth,height=0.42\textheight,keepaspectratio]{{{profile}}}' if profile else 'Perfil no disponible.'}
\end{{minipage}}
{_title_block(summary, location, 2, 'Subcuencas y perfil longitudinal del cauce principal')}

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
            cwd=str(work_dir), capture_output=True, text=True, timeout=240, check=False,
        )
    except Exception as exc:
        return None, str(exc)
    pdf_path = resolved_output_dir / f"{tex_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        detail = (completed.stderr or completed.stdout or "Error desconocido de compilación").strip()
        return None, detail[-2200:]
    return pdf_path, None


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None, main_channel=None) -> dict:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outlet = summary.get("outlet_original") or {}
    location = resolve_administrative_location(float(outlet.get("y", 0)), float(outlet.get("x", 0)))
    summary.update(location)
    summary["location_label"] = location_label(location)
    summary["site_name"] = _site_name(summary, location)

    satellite = _satellite_location_figure(output_dir, summary, location)
    if satellite:
        figures["location_satellite"] = satellite

    tex_path = output_dir / "informe_hydrobasin.tex"
    plan_tex_path = output_dir / "plano_hidrografico.tex"
    tex_path.write_text(_report_tex(summary, figures, subbasins, location), encoding="utf-8")
    plan_tex_path.write_text(_plan_tex(summary, figures, location), encoding="utf-8")

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
