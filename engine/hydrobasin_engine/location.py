from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

COLOMBIA_ISO3 = "COL"
COLOMBIA_MUNICIPALITIES_LAYER = "https://services9.arcgis.com/pZylgd2zhNey2qXF/arcgis/rest/services/Mapa_de_los_municipios_de_Colombia_con_datos_del_MinTic_WFL1/FeatureServer/1"
WORLD_COUNTRIES_LAYER = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/World_Countries/FeatureServer/0"


def _query(layer: str, lat: float, lon: float, out_fields: str) -> dict | None:
    params = urlencode({
        "f": "json",
        "where": "1=1",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
        "resultRecordCount": "1",
    })
    request = Request(f"{layer}/query?{params}", headers={"User-Agent": "HydroBasin/1.0"})
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError("ArcGIS devolvió un error al resolver la ubicación.")
    features = payload.get("features") or []
    return features[0].get("attributes") if features else None


def _format_name(val: str) -> str:
    if not val:
        return ""
    words = val.strip().split()
    lowers = {"de", "del", "la", "las", "el", "los", "y", "en"}
    result = []
    for i, w in enumerate(words):
        wl = w.lower()
        if i > 0 and wl in lowers:
            result.append(wl)
        else:
            result.append(w.capitalize())
    return " ".join(result)


def resolve_administrative_location(lat: float, lon: float) -> dict:
    """Identifica el país y municipio/departamento mediante ArcGIS."""
    base = {
        "country": "",
        "country_code": "",
        "department": "",
        "department_code": "",
        "municipality": "",
        "municipality_code": "",
        "location_resolved": False,
        "location_source": "ArcGIS",
    }
    try:
        country = _query(WORLD_COUNTRIES_LAYER, lat, lon, "FID,COUNTRY,ISO_CC,CONTINENT,COUNTRYAFF")
        if not country:
            return base
        code = str(country.get("ISO_CC") or "").upper()
        name = _format_name(str(country.get("COUNTRYAFF") or country.get("COUNTRY") or ""))
        base.update({"country": name, "country_code": code, "location_resolved": bool(name)})
        if code != COLOMBIA_ISO3:
            return base

        municipality = _query(
            COLOMBIA_MUNICIPALITIES_LAYER,
            lat,
            lon,
            "DPTO_CCDGO,DPTO_CNMBR,MPIO_CCDGO,MPIO_CNMBR",
        )
        if municipality:
            base.update({
                "department": _format_name(str(municipality.get("DPTO_CNMBR") or "")),
                "department_code": str(municipality.get("DPTO_CCDGO") or "").strip(),
                "municipality": _format_name(str(municipality.get("MPIO_CNMBR") or "")),
                "municipality_code": str(municipality.get("MPIO_CCDGO") or "").strip(),
            })
        return base
    except Exception:
        return base


def location_label(location: dict) -> str:
    country = location.get("country") or "Ubicación no determinada"
    if str(location.get("country_code") or "").upper() == COLOMBIA_ISO3:
        municipality = location.get("municipality") or "Municipio no determinado"
        department = location.get("department") or "Departamento no determinado"
        return f"{municipality}, {department}, {country}"
    return str(country)
