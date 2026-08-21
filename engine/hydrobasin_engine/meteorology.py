from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

IDEAM_DATASET_URL = "https://www.datos.gov.co/resource/hp9r-jxuu.json"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _clean_text(val: Any) -> str:
    if val is None:
        return ""
    return " ".join(str(val).strip().split())


def normalize_station_records(
    stations: list[dict[str, Any]],
    center_lat: float,
    center_lon: float,
) -> list[dict[str, Any]]:
    """Normaliza estaciones suministradas sin alterar códigos oficiales."""
    normalized: list[dict[str, Any]] = []
    for item in stations:
        try:
            lat = float(item.get("latitud"))
            lon = float(item.get("longitud"))
        except (TypeError, ValueError):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue

        alt_val = None
        if item.get("altitud") not in (None, ""):
            try:
                alt_val = float(item.get("altitud"))
            except (TypeError, ValueError):
                alt_val = None

        distance = item.get("distancia_km")
        try:
            distance_value = float(distance) if distance is not None else _haversine_km(center_lat, center_lon, lat, lon)
        except (TypeError, ValueError):
            distance_value = _haversine_km(center_lat, center_lon, lat, lon)

        normalized.append({
            "codigo": _clean_text(item.get("codigo")) or "N/D",
            "nombre": _clean_text(item.get("nombre")) or "N/D",
            "categoria": _clean_text(item.get("categoria")) or "N/D",
            "tecnologia": _clean_text(item.get("tecnologia")) or "N/D",
            "estado": _clean_text(item.get("estado")) or "N/D",
            "departamento": _clean_text(item.get("departamento")),
            "municipio": _clean_text(item.get("municipio")),
            "latitud": round(lat, 6),
            "longitud": round(lon, 6),
            "altitud": alt_val,
            "distancia_km": round(distance_value, 3),
            "entidad": _clean_text(item.get("entidad")) or "IDEAM",
            "source": item.get("source") or "user",
        })
    normalized.sort(key=lambda s: s["distancia_km"])
    return normalized


def fetch_ideam_stations(
    center_lat: float,
    center_lon: float,
    department: str = "",
    radius_km: float = 50.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Consulta el catálogo oficial abierto de estaciones del IDEAM.

    Si la fuente oficial no responde o no hay estaciones suficientes, se retorna una
    lista vacía o parcial. HydroBasin nunca crea estaciones ficticias como respaldo.
    """
    if radius_km <= 0:
        raise ValueError("El radio de búsqueda de estaciones debe ser mayor que cero.")
    if limit <= 0:
        return []

    stations: list[dict[str, Any]] = []
    query_url = f"{IDEAM_DATASET_URL}?$limit=1000"
    if department:
        dep_clean = department.upper().replace(" DEPARTAMENTO", "").strip()
        dep_sql = dep_clean.replace("'", "''")
        where = f"upper(departamento) like '%{dep_sql}%'"
        query_url += "&$where=" + urllib.parse.quote(where, safe="()='%")

    try:
        req = urllib.request.Request(query_url, headers={"User-Agent": "HydroBasin/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    for item in raw:
        try:
            location = item.get("ubicaci_n") or {}
            lat = float(item.get("latitud") or location.get("latitude"))
            lon = float(item.get("longitud") or location.get("longitude"))
        except (ValueError, TypeError, AttributeError):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue

        distance = _haversine_km(center_lat, center_lon, lat, lon)
        if distance > radius_km:
            continue

        altitude = None
        try:
            if item.get("altitud") not in (None, ""):
                altitude = float(item.get("altitud"))
        except (ValueError, TypeError):
            altitude = None

        name = _clean_text(item.get("nombre"))
        if "[" in name:
            name = name.split("[")[0].strip()

        stations.append({
            "codigo": _clean_text(item.get("codigo")) or "N/D",
            "nombre": name.title() if name else "N/D",
            "categoria": _clean_text(item.get("categoria")) or "N/D",
            "tecnologia": _clean_text(item.get("tecnologia")) or "N/D",
            "estado": _clean_text(item.get("estado")) or "N/D",
            "departamento": _clean_text(item.get("departamento")).title(),
            "municipio": _clean_text(item.get("municipio")).title(),
            "latitud": round(lat, 6),
            "longitud": round(lon, 6),
            "altitud": altitude,
            "distancia_km": round(distance, 3),
            "entidad": _clean_text(item.get("entidad")) or "IDEAM",
            "source": "IDEAM datos.gov.co",
        })

    stations.sort(key=lambda s: s["distancia_km"])
    return stations[:limit]


def plot_stations_map(
    output_path: Path,
    stations: list[dict[str, Any]],
    watershed,
    center_lat: float,
    center_lon: float,
    loc: dict,
) -> str | None:
    if not stations:
        return None

    try:
        fig, ax = plt.subplots(figsize=(8.5, 6.2), dpi=200)
        if watershed is not None and not watershed.empty:
            watershed.to_crs("EPSG:4326").plot(ax=ax, alpha=0.3, linewidth=1.5, label="Cuenca Hidrográfica")

        ax.scatter([center_lon], [center_lat], s=130, zorder=5, marker="^", label="Exutorio")
        ax.scatter(
            [s["longitud"] for s in stations],
            [s["latitud"] for s in stations],
            s=85,
            zorder=4,
            marker="o",
            label="Estaciones",
        )

        for station in stations:
            ax.annotate(
                f"{station['nombre']} ({station['distancia_km']:.1f} km)",
                (station["longitud"], station["latitud"]),
                xytext=(6, 6),
                textcoords="offset points",
                fontsize=7.5,
            )

        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        ax.set_xlabel("Longitud (WGS84)", fontsize=8.5)
        ax.set_ylabel("Latitud (WGS84)", fontsize=8.5)
        ax.tick_params(labelsize=8)
        ax.legend(loc="best", fontsize=8)
        ax.set_title(
            f"Red de estaciones meteorológicas — {loc.get('municipality', 'Área de estudio')}",
            fontsize=10.5,
            fontweight="bold",
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return str(output_path)
    except Exception:
        return None
