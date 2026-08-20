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

from .location import location_label, resolve_administrative_location


def _n(value, digits=2):
    return "N/D" if value is None else f"{value:.{digits}f}"


def _esc(value) -> str:
    text = str(value or "")
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}"}
    return "".join(replacements.get(ch, ch) for ch in text)


def _tc_min(summary: dict, key: str):
    value = summary.get(key)
    return None if value is None else float(value) * 60.0


def _site(summary: dict, loc: dict) -> str:
    project = str(summary.get("project_name") or "").strip()
    if project and project.lower() not in {"cuenca sin título", "cuenca sin titulo"}:
        return project
    if loc.get("country_code") == "COL" and loc.get("municipality"):
        return f"Cuenca aportante - {loc['municipality']}, {loc.get('department') or 'Colombia'}"
    if loc.get("country"):
        return f"Cuenca aportante - {loc['country']}"
    return "Cuenca aportante al exutorio seleccionado"


def _admin_label(loc: dict) -> str:
    if loc.get("country_code") == "COL":
        return ", ".join(v for v in [loc.get("municipality"), loc.get("department"), loc.get("country")] if v) or "Colombia"
    return loc.get("country") or "Ubicación no determinada"


def _satellite_map(output_dir: Path, summary: dict, loc: dict) -> str | None:
    outlet = summary.get("outlet_original") or {}
    lat, lon = outlet.get("y"), outlet.get("x")
    if lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)
    dlat = 0.055
    dlng = dlat / max(0.25, abs(math.cos(math.radians(lat))))
    params = urlencode({
        "bbox": f"{lon-dlng},{lat-dlat},{lon+dlng},{lat+dlat}",
        "bboxSR": "4326", "imageSR": "4326", "size": "1400,850",
        "format": "png32", "transparent": "false", "f": "image",
    })
    try:
        req = Request(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + params,
            headers={"User-Agent": "HydroBasin/1.0"},
        )
        with urlopen(req, timeout=25) as response:
            image = plt.imread(BytesIO(response.read()), format="png")
        fig, ax = plt.subplots(figsize=(11.5, 6.5))
        ax.imshow(image, extent=[lon-dlng, lon+dlng, lat-dlat, lat+dlat])
        ax.scatter([lon], [lat], s=130, facecolor="#ef4444", edgecolor="white", linewidth=2.2, zorder=4)
        ax.annotate("Exutorio", (lon, lat), xytext=(10, 10), textcoords="offset points", color="white", fontsize=10,
                    fontweight="bold", bbox={"boxstyle": "round,pad=.25", "fc": "#111827", "alpha": .80, "ec": "none"})
        ax.set_title(f"Localización satelital - {_admin_label(loc)}", fontsize=12, fontweight="bold")
        ax.set_xlabel("Longitud")
        ax.set_ylabel("Latitud")
        path = output_dir / "figuras" / "00_ubicacion_satelital.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return "figuras/00_ubicacion_satelital.png"
    except Exception:
        return None


def _metadata_table(summary: dict, loc: dict) -> str:
    outlet = summary.get("outlet_original") or {}
    snapped = summary.get("outlet_snapped") or {}
    res = summary.get("metric_resolution_m") or []
    resolution = " x ".join(f"{v:.1f}" for v in res) + " m" if res else "N/D"
    return rf"""
\begin{{tabular}}{{p{{4.6cm}}p{{10.3cm}}}}
\toprule
\textbf{{Dato}} & \textbf{{Información}} \\
\midrule
Ubicación & {_esc(_admin_label(loc))} \\
Coordenadas del exutorio & {_n(outlet.get('y'),6)}, {_n(outlet.get('x'),6)} ({_esc(outlet.get('crs') or 'EPSG:4326')}) \\
Exutorio ajustado & {_n(snapped.get('y'),6)}, {_n(snapped.get('x'),6)} ({_esc(snapped.get('crs') or summary.get('crs_dem') or 'N/D')}) \\
Fuente del DEM & {_esc(summary.get('dem_source') or 'N/D')} \\
CRS del DEM & {_esc(summary.get('crs_dem') or 'N/D')} \\
CRS de cálculo & {_esc(summary.get('crs_calculo') or 'N/D')} \\
Resolución aproximada & {_esc(resolution)} \\
Área delimitada & {_n(summary.get('area_km2'))} km$^2$ \\
\bottomrule
\end{{tabular}}
"""


def _subbasin_table(subbasins, limit=20) -> str:
    if subbasins is None or subbasins.empty or "area_km2" not in subbasins.columns:
        return ""
    top = subbasins.sort_values("area_km2", ascending=False).head(limit)
    rows = "\n".join(f"{int(r['subbasin_id'])} & {_n(float(r['area_km2']),2)} \\\\" for _, r in top.iterrows())
    return rf"""\begin{{center}}\begin{{tabular}}{{rr}}\toprule\textbf{{ID}} & \textbf{{Área (km$^2$)}} \\\midrule
{rows}
\bottomrule\end{{tabular}}\end{{center}}"""


def _report(summary: dict, figures: dict[str, str], subbasins, loc: dict) -> str:
    site = _site(summary, loc)
    admin = _admin_label(loc)
    outlet = summary.get("outlet_original") or {}
    sat = figures.get("location_satellite")
    profile = figures.get("profile")
    subfig = figures.get("subbasins")
    tc_k, tc_t, tc_p = (_tc_min(summary, k) for k in ("tc_kirpich_h", "tc_temez_h", "tc_promedio_h"))
    desnivel = (summary.get("main_channel_elevation_source_m") or 0) - (summary.get("main_channel_elevation_outlet_m") or 0)

    sat_tex = rf"\begin{{figure}}[H]\centering\includegraphics[width=.94\textwidth]{{{sat}}}\caption{{Localización satelital del punto de análisis. Fuente: Esri World Imagery.}}\end{{figure}}" if sat else ""
    profile_tex = rf"\begin{{figure}}[H]\centering\includegraphics[width=.93\textwidth]{{{profile}}}\caption{{Perfil longitudinal del cauce principal.}}\end{{figure}}" if profile else ""
    sub_tex = ""
    if subbasins is not None and not subbasins.empty:
        sub_tex = rf"""
\section{{Subcuencas}}
Se identificaron \textbf{{{len(subbasins)}}} subcuencas dentro de la cuenca principal. Estas unidades permiten interpretar la distribución espacial de los aportes y la forma en que los drenajes secundarios se integran progresivamente al sistema principal. La tabla presenta las unidades de mayor área y el mapa muestra la subdivisión completa.
{_subbasin_table(subbasins)}
{rf'\begin{{figure}}[H]\centering\includegraphics[width=.91\textwidth]{{{subfig}}}\caption{{Subcuencas hidrológicas, red de drenaje y cauce principal.}}\end{{figure}}' if subfig else ''}
"""

    intro = f"El presente informe técnico corresponde al análisis de {site}, localizado en {admin}. El estudio se desarrolla a partir de un Modelo Digital de Elevación y de las coordenadas del punto de salida seleccionado, con el propósito de obtener una representación reproducible de la cuenca aportante y de su organización hidrográfica. El procesamiento permite reconocer la divisoria de aguas, la red de drenaje, la jerarquía de corrientes, las subcuencas internas y el cauce principal, complementando estos resultados con parámetros morfométricos que describen la configuración física del sistema."
    scope = f"El alcance para {site} comprende el acondicionamiento hidrológico del DEM, la determinación de dirección y acumulación de flujo, el ajuste del exutorio, la delimitación de la cuenca, la extracción y jerarquización de la red, la subdivisión en subcuencas y la identificación del cauce principal con su perfil longitudinal. También se calculan indicadores geométricos e hidrológicos y se generan productos cartográficos y GIS. Los resultados constituyen un insumo de caracterización y deben contrastarse con información oficial, observaciones de campo y datos hidrometeorológicos cuando se utilicen en estudios de diseño."
    objective = f"Delimitar y caracterizar {site}, ubicado en {admin}, mediante el procesamiento de un Modelo Digital de Elevación y el análisis de su estructura de drenaje, obteniendo parámetros morfométricos, hidrológicos y cartográficos útiles para la comprensión de la cuenca."

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}\usepackage[T1]{{fontenc}}\usepackage[spanish]{{babel}}
\usepackage{{geometry}}\usepackage{{graphicx}}\usepackage{{booktabs}}\usepackage{{float}}\usepackage{{xcolor}}\usepackage{{fancyhdr}}\usepackage{{array}}
\geometry{{margin=2.25cm}}\definecolor{{hb}}{{HTML}}{{176B73}}
\pagestyle{{fancy}}\fancyhf{{}}\lhead{{HydroBasin}}\rhead{{Informe de análisis de cuenca}}\cfoot{{\thepage}}
\begin{{document}}
\begin{{titlepage}}\vspace*{{1.4cm}}{{\color{{hb}}\Large\bfseries HYDROBASIN / WATERSHED STUDIO}}\\[.55cm]
{{\Huge\bfseries Informe de delimitación y análisis de cuenca hidrográfica}}\\[.45cm]
{{\Large {_esc(site)}}}\\[1.2cm]
{_metadata_table(summary, loc)}
\vfill{{\small Documento técnico generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}.}}\end{{titlepage}}
\tableofcontents\newpage

\section{{Introducción}}
{_esc(intro)}

\section{{Alcance}}
{_esc(scope)}

\section{{Objetivos}}
\subsection*{{Objetivo general}}
{_esc(objective)}
\subsection*{{Objetivos específicos}}
\begin{{itemize}}
\item Acondicionar hidrológicamente el DEM correspondiente a {_esc(site)} conservando la resolución utilizada en el análisis.
\item Determinar dirección y acumulación de flujo y delimitar la cuenca aportante al exutorio seleccionado.
\item Extraer y jerarquizar la red de drenaje e identificar las subcuencas internas.
\item Determinar el cauce principal, su longitud, desnivel, pendiente y perfil longitudinal.
\item Generar parámetros morfométricos, cartografía técnica y productos GIS para {_esc(admin)}.
\end{{itemize}}

\section{{Ubicación}}
{_esc(site)} se localiza en \textbf{{{_esc(admin)}}}. El punto definido como exutorio se encuentra en las coordenadas \textbf{{{_n(outlet.get('y'),6)}, {_n(outlet.get('x'),6)}}} en EPSG:4326. La identificación territorial se realiza mediante consulta espacial a capas públicas de ArcGIS, aplicando el mismo criterio territorial utilizado en el módulo de Cotizaciones del SGI: dentro de Colombia se obtiene municipio y departamento; fuera del país se conserva el país como referencia administrativa principal.
{sat_tex}

\section{{Datos de entrada y referencia espacial}}
{_metadata_table(summary, loc)}

\section{{Metodología}}
El procesamiento de {_esc(site)} inicia con la lectura y validación del Modelo Digital de Elevación, verificando su cobertura, resolución y sistema de referencia. Posteriormente se acondiciona la superficie mediante la corrección de pits, depresiones y zonas planas para obtener continuidad hidrológica sin disminuir la resolución espacial empleada en el análisis. Sobre esta superficie se calcula la dirección de flujo con el esquema D8 y la acumulación de flujo para cada celda, lo cual permite reconocer las trayectorias preferenciales de escorrentía derivadas de la topografía.

El punto seleccionado se ajusta a una celda con acumulación significativa para reducir errores asociados a pequeñas diferencias de posicionamiento. A partir del exutorio ajustado se delimita la cuenca aportante y se vectoriza su divisoria. La red de drenaje se extrae utilizando un área mínima de aporte de {_n(summary.get('minimum_area_km2'),3)} km$^2$, equivalente aproximadamente a {_n(summary.get('drainage_threshold'),0)} celdas, y posteriormente se jerarquiza mediante el orden de Strahler. La estructura de flujo D8 se utiliza además para establecer las subcuencas internas. Finalmente, el cauce principal se traza desde el exutorio hacia la cabecera siguiendo la conectividad aguas arriba de mayor acumulación; con su longitud y diferencia altimétrica se obtiene la pendiente media y se estiman los tiempos de concentración mediante las formulaciones empíricas de Kirpich y Témez.

\section{{Resultados hidrológicos y morfométricos}}
\begin{{center}}\begin{{tabular}}{{p{{8.2cm}}r}}\toprule\textbf{{Parámetro}} & \textbf{{Resultado}} \\\midrule
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
\bottomrule\end{{tabular}}\end{{center}}

\section{{Cauce principal y tiempo de concentración}}
El cauce principal representa la trayectoria dominante de evacuación del flujo dentro de {_esc(site)}. Se obtuvo una longitud de \textbf{{{_n(summary.get('main_channel_length_km'))} km}}, con una pendiente media de \textbf{{{_n(summary.get('main_channel_slope_percent'),3)}\%}} y un desnivel aproximado de \textbf{{{_n(desnivel)} m}}. El perfil longitudinal permite reconocer la variación altimétrica desde el exutorio hasta la cabecera y constituye una referencia para interpretar el gradiente general del sistema.
\begin{{center}}\begin{{tabular}}{{p{{8.5cm}}r}}\toprule\textbf{{Parámetro}} & \textbf{{Resultado}} \\\midrule
Longitud del cauce principal & {_n(summary.get('main_channel_length_km'))} km \\
Elevación en cabecera & {_n(summary.get('main_channel_elevation_source_m'))} m \\
Elevación en exutorio & {_n(summary.get('main_channel_elevation_outlet_m'))} m \\
Desnivel & {_n(desnivel)} m \\
Pendiente media & {_n(summary.get('main_channel_slope_percent'),3)}\% \\
Tiempo de concentración Kirpich & {_n(tc_k)} min \\
Tiempo de concentración Témez & {_n(tc_t)} min \\
Tiempo de concentración promedio & {_n(tc_p)} min \\
\bottomrule\end{{tabular}}\end{{center}}
{profile_tex}

{sub_tex}

\section{{Cartografía técnica}}
Para evitar redundancias se incluyen únicamente productos que aportan información diferente. El mapa de subcuencas y el perfil longitudinal se presentan en sus secciones temáticas; en esta sección se conserva el contexto del DEM, la acumulación de flujo, la cuenca con la red y el cauce principal, y el orden de Strahler.
\begin{{figure}}[H]\centering\includegraphics[width=.91\textwidth]{{{figures.get('dem','')}}}\caption{{Contexto del Modelo Digital de Elevación y cuenca delimitada.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=.91\textwidth]{{{figures.get('accumulation','')}}}\caption{{Acumulación de flujo dentro de la cuenca.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=.91\textwidth]{{{figures.get('watershed','')}}}\caption{{Cuenca principal, red de drenaje y cauce principal.}}\end{{figure}}
\begin{{figure}}[H]\centering\includegraphics[width=.91\textwidth]{{{figures.get('strahler','')}}}\caption{{Jerarquía de corrientes según el orden de Strahler.}}\end{{figure}}

\section{{Análisis e interpretación}}
Los parámetros geométricos deben analizarse de forma conjunta. Para {_esc(site)}, el factor de forma es {_n(summary.get('factor_forma'),3)} y el índice de compacidad de Gravelius es {_n(summary.get('coeficiente_compacidad'),3)}; estos valores describen cómo se distribuye la superficie respecto a las longitudes características de la cuenca y condicionan las distancias de recorrido hacia el exutorio. La densidad de drenaje calculada es {_n(summary.get('densidad_drenaje_km_km2'),3)} km/km$^2$ y depende directamente del umbral adoptado para extraer la red, por lo que representa una red derivada del DEM y no un inventario de cauces validado en campo.

El cauce principal, su pendiente y el relieve total permiten reconocer el gradiente topográfico dominante. La subdivisión en subcuencas muestra cómo se organizan espacialmente los aportes antes de incorporarse al sistema principal. Los tiempos de concentración obtenidos son estimaciones empíricas y deben contrastarse con información del proyecto cuando se empleen en modelación o diseño hidráulico.

\section{{Conclusiones}}
El procesamiento permitió delimitar {_esc(site)} e integrar en una misma base técnica la divisoria de aguas, la red de drenaje, las subcuencas, el cauce principal y sus principales parámetros morfométricos. Los productos obtenidos proporcionan una referencia reproducible para análisis posteriores y pueden incorporarse en plataformas SIG o procesos de revisión técnica.

La ubicación administrativa y las coordenadas del exutorio quedan documentadas como parte de la trazabilidad del estudio. Para Colombia, la asociación municipio-departamento se obtiene directamente mediante consulta espacial a la cartografía de ArcGIS; para ubicaciones internacionales se conserva el país como referencia territorial principal.

\section{{Limitaciones}}
Los resultados dependen de la calidad y resolución del DEM, de su acondicionamiento, de la posición del exutorio y del área mínima de aporte. HydroBasin no infiere precipitación, temperatura, caudales observados, cobertura o parámetros de suelo. La identificación administrativa debe verificarse cuando el punto se encuentre próximo a límites territoriales.
\end{{document}}
"""


def _title_block(summary: dict, loc: dict, sheet: int, title: str) -> str:
    outlet = summary.get("outlet_original") or {}
    return rf"""\vspace{{1.2mm}}
\begin{{tabular}}{{|p{{3.0cm}}|p{{7.0cm}}|p{{3.1cm}}|p{{4.8cm}}|p{{3.0cm}}|}}\hline
\textbf{{PROYECTO}} & \multicolumn{{4}}{{l|}}{{{_esc(_site(summary, loc))}}} \\\hline
\textbf{{PLANO}} & \multicolumn{{2}}{{l|}}{{{_esc(title)}}} & \textbf{{HOJA}} & {sheet} de 2 \\\hline
\textbf{{UBICACIÓN}} & \multicolumn{{2}}{{l|}}{{{_esc(_admin_label(loc))}}} & \textbf{{FECHA}} & {datetime.now().strftime('%d/%m/%Y')} \\\hline
\textbf{{EXUTORIO}} & \multicolumn{{2}}{{l|}}{{{_n(outlet.get('y'),6)}, {_n(outlet.get('x'),6)}}} & \textbf{{CRS}} & {_esc(summary.get('crs_calculo') or 'N/D')} \\\hline
\textbf{{DEM}} & \multicolumn{{2}}{{l|}}{{{_esc(summary.get('dem_source') or 'N/D')}}} & \textbf{{ÁREA}} & {_n(summary.get('area_km2'))} km$^2$ \\\hline
\multicolumn{{3}}{{|l|}}{{HydroBasin / Watershed Studio}} & \textbf{{VERSIÓN}} & 1.0 \\\hline
\end{{tabular}}"""


def _plan(summary: dict, figures: dict[str, str], loc: dict) -> str:
    tc_k = _tc_min(summary, "tc_kirpich_h")
    second_main = figures.get("subbasins") or figures.get("watershed") or figures.get("plan")
    profile = figures.get("profile")
    profile_tex = rf"\includegraphics[width=\linewidth,height=.42\textheight,keepaspectratio]{{{profile}}}" if profile else "Perfil no disponible."
    return rf"""\documentclass[9pt]{{article}}
\usepackage[utf8]{{inputenc}}\usepackage[T1]{{fontenc}}\usepackage[spanish]{{babel}}\usepackage[a3paper,landscape,margin=8mm]{{geometry}}
\usepackage{{graphicx}}\usepackage{{array}}\usepackage{{booktabs}}\pagestyle{{empty}}\begin{{document}}
\begin{{center}}{{\LARGE\bfseries PLANO HIDROGRÁFICO - DELIMITACIÓN GENERAL Y RED DE DRENAJE}}\end{{center}}
\begin{{minipage}}[t]{{.79\textwidth}}\centering\includegraphics[width=\linewidth,height=.72\textheight,keepaspectratio]{{{figures.get('plan','')}}}\end{{minipage}}\hfill
\begin{{minipage}}[t]{{.19\textwidth}}\small\textbf{{CUADRO TÉCNICO}}\\[1mm]
\begin{{tabular}}{{@{{}}lr@{{}}}}Área & {_n(summary.get('area_km2'))} km$^2$\\Perímetro & {_n(summary.get('perimetro_km'))} km\\Compacidad & {_n(summary.get('coeficiente_compacidad'),3)}\\Circularidad & {_n(summary.get('relacion_circularidad'),3)}\\Dens. drenaje & {_n(summary.get('densidad_drenaje_km_km2'),3)}\\Strahler máx. & {summary.get('strahler_max','N/D')}\\Subcuencas & {summary.get('subbasin_count','N/D')}\\Cauce principal & {_n(summary.get('main_channel_length_km'))} km\\Pendiente & {_n(summary.get('main_channel_slope_percent'),2)}\%\\Tc Kirpich & {_n(tc_k)} min\\\end{{tabular}}\end{{minipage}}
{_title_block(summary, loc, 1, 'Delimitación general, subcuencas, drenajes y cauce principal')}
\newpage
\begin{{center}}{{\LARGE\bfseries PLANO HIDROGRÁFICO - SUBCUENCAS Y PERFIL DEL CAUCE PRINCIPAL}}\end{{center}}
\begin{{minipage}}[t]{{.60\textwidth}}\centering\includegraphics[width=\linewidth,height=.63\textheight,keepaspectratio]{{{second_main}}}\end{{minipage}}\hfill
\begin{{minipage}}[t]{{.38\textwidth}}\textbf{{CAUCE PRINCIPAL}}\\[1.5mm]
Longitud: {_n(summary.get('main_channel_length_km'))} km\\Elevación cabecera: {_n(summary.get('main_channel_elevation_source_m'))} m\\Elevación exutorio: {_n(summary.get('main_channel_elevation_outlet_m'))} m\\Pendiente media: {_n(summary.get('main_channel_slope_percent'),3)}\%\\Tc Kirpich: {_n(tc_k)} min\\[3mm]
\textbf{{PERFIL LONGITUDINAL}}\\[1mm]{profile_tex}\end{{minipage}}
{_title_block(summary, loc, 2, 'Subcuencas y perfil longitudinal del cauce principal')}
\end{{document}}"""


def _find_tectonic() -> str | None:
    return shutil.which("tectonic") or shutil.which("tectonic.exe")


def _compile(tex: Path, output_dir: Path):
    compiler = _find_tectonic()
    if not compiler:
        return None, "Tectonic no está disponible en PATH."
    out = output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run([compiler, tex.name, "--outdir", str(out)], cwd=str(tex.parent.resolve()), capture_output=True, text=True, timeout=240, check=False)
    except Exception as exc:
        return None, str(exc)
    pdf = out / f"{tex.stem}.pdf"
    if proc.returncode != 0 or not pdf.exists():
        return None, (proc.stderr or proc.stdout or "Error desconocido")[-2200:]
    return pdf, None


def generar_informes(output_dir: Path, summary: dict, figures: dict[str, str], subbasins=None, main_channel=None) -> dict:
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    outlet = summary.get("outlet_original") or {}
    loc = resolve_administrative_location(float(outlet.get("y", 0)), float(outlet.get("x", 0)))
    summary.update(loc)
    summary["location_label"] = location_label(loc)
    summary["site_name"] = _site(summary, loc)
    sat = _satellite_map(output_dir, summary, loc)
    if sat:
        figures["location_satellite"] = sat
    report_tex = output_dir / "informe_hydrobasin.tex"
    plan_tex = output_dir / "plano_hidrografico.tex"
    report_tex.write_text(_report(summary, figures, subbasins, loc), encoding="utf-8")
    plan_tex.write_text(_plan(summary, figures, loc), encoding="utf-8")
    report_pdf, e1 = _compile(report_tex, output_dir)
    plan_pdf, e2 = _compile(plan_tex, output_dir)
    errors = [e for e in (e1, e2) if e]
    return {"tex": report_tex.name, "pdf": report_pdf.name if report_pdf else None, "plan_tex": plan_tex.name, "plan_pdf": plan_pdf.name if plan_pdf else None,
            "compiled": bool(report_pdf and plan_pdf), "compiler_found": bool(_find_tectonic()), "compile_error": " | ".join(errors) if errors else None}
