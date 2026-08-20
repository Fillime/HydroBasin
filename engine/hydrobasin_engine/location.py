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


def resolve_administrative_location(lat: float, lon: float) -> dict:
    """Replica el criterio territorial usado por SGI Cotizaciones.

    Primero identifica el país mediante ArcGIS World Countries. Para Colombia
    consulta además la capa municipal y devuelve municipio/departamento. Fuera
    de Colombia el informe conserva únicamente el país como ubicación administrativa.
    """
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
        name = str(country.get("COUNTRYAFF") or country.get("COUNTRY") or "").strip()
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
                "department": str(municipality.get("DPTO_CNMBR") or "").strip(),
                "department_code": str(municipality.get("DPTO_CCDGO") or "").strip(),
                "municipality": str(municipality.get("MPIO_CNMBR") or "").strip(),
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
