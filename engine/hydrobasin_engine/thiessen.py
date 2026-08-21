from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import Voronoi
from shapely.geometry import Point, Polygon


def compute_thiessen_polygons(
    stations: list[dict[str, Any]],
    watershed_gdf: gpd.GeoDataFrame,
    output_fig_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Calcula los polígonos de Thiessen recortados a la cuenca y sus ponderaciones de área métricas."""
    if watershed_gdf is None or watershed_gdf.empty or len(stations) == 0:
        return [], None

    # Garantizar CRS métrico proyectado (UTM) para que las áreas sean en metros cuadrados
    if watershed_gdf.crs and watershed_gdf.crs.is_geographic:
        try:
            utm_crs = watershed_gdf.estimate_utm_crs() or "EPSG:32618"
        except Exception:
            utm_crs = "EPSG:32618"
        w_utm = watershed_gdf.to_crs(utm_crs)
    else:
        w_utm = watershed_gdf.copy()

    metric_crs = w_utm.crs
    basin_poly = w_utm.unary_union
    total_area_km2 = max(0.001, basin_poly.area / 1e6)

    # Si hay 1 o 2 estaciones, repartir equitativamente
    if len(stations) < 3:
        n_st = len(stations)
        equal_weight = 100.0 / n_st
        weights = []
        for s in stations:
            weights.append({
                "codigo": s["codigo"],
                "nombre": s["nombre"],
                "area_km2": round(total_area_km2 / n_st, 2),
                "porcentaje": round(equal_weight, 1),
            })
        return weights, None

    # Convertir estaciones a GeoDataFrame métrico
    pts = [Point(float(s["longitud"]), float(s["latitud"])) for s in stations]
    st_gdf = gpd.GeoDataFrame(stations, geometry=pts, crs="EPSG:4326").to_crs(metric_crs)

    coords = np.array([[geom.x, geom.y] for geom in st_gdf.geometry])

    # Construir caja envolvente amplia para cerrar Voronoi
    minx, miny, maxx, maxy = basin_poly.bounds
    dx = max(10000.0, (maxx - minx) * 4.0)
    dy = max(10000.0, (maxy - miny) * 4.0)
    box_pts = np.array([
        [minx - dx, miny - dy],
        [maxx + dx, miny - dy],
        [maxx + dx, maxy + dy],
        [minx - dx, maxy + dy],
    ])
    all_coords = np.vstack([coords, box_pts])

    vor = Voronoi(all_coords)

    # Reconstruir regiones finitas
    station_polys = []
    for i in range(len(coords)):
        region_idx = vor.point_region[i]
        region = vor.regions[region_idx]
        if not region or -1 in region:
            continue
        poly_coords = [vor.vertices[v] for v in region]
        try:
            poly = Polygon(poly_coords)
            clipped = poly.intersection(basin_poly)
            if not clipped.is_empty:
                st_area = clipped.area / 1e6
                if st_area > 0.0001:
                    station_polys.append({
                        "codigo": stations[i]["codigo"],
                        "nombre": stations[i]["nombre"],
                        "geometry": clipped,
                        "area_km2": st_area,
                    })
        except Exception:
            continue

    if not station_polys:
        station_polys = [
            {
                "codigo": s["codigo"],
                "nombre": s["nombre"],
                "geometry": basin_poly,
                "area_km2": total_area_km2 / len(stations),
            }
            for s in stations
        ]

    calc_total_area = sum(p["area_km2"] for p in station_polys) or total_area_km2
    weights = []
    for p in station_polys:
        pct = (p["area_km2"] / calc_total_area) * 100.0
        weights.append({
            "codigo": p["codigo"],
            "nombre": p["nombre"],
            "area_km2": round(float(p["area_km2"]), 2),
            "porcentaje": round(float(pct), 1),
        })

    # Generar figura temática si se requiere
    if output_fig_path:
        try:
            output_fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig, ax = plt.subplots(figsize=(8.5, 6.2), dpi=200)

            # Dibujar cuenca de fondo
            w_deg = watershed_gdf.to_crs("EPSG:4326")
            w_deg.plot(ax=ax, facecolor="none", edgecolor="#0f172a", linewidth=1.6, zorder=3)

            # Dibujar polígonos recortados
            thiessen_gdf = gpd.GeoDataFrame(station_polys, crs=metric_crs).to_crs("EPSG:4326")
            colors = ["#fef08a", "#bae6fd", "#bbf7d0", "#fed7aa", "#e9d5ff", "#fbcfe8"]
            thiessen_gdf.plot(
                ax=ax,
                color=[colors[i % len(colors)] for i in range(len(thiessen_gdf))],
                edgecolor="#475569",
                linewidth=1.0,
                alpha=0.65,
                zorder=2,
            )

            # Estaciones
            st_deg = st_gdf.to_crs("EPSG:4326")
            st_deg.plot(ax=ax, color="#dc2626", markersize=48, edgecolor="white", linewidth=1.2, zorder=5)

            for _, r in st_deg.iterrows():
                ax.annotate(
                    r["nombre"],
                    (r.geometry.x, r.geometry.y),
                    xytext=(0, 7),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7.5,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=.2", fc="white", ec="#cbd5e1", alpha=0.9),
                    zorder=6,
                )

            ax.set_title("Polígonos de Thiessen e Influencia sobre la Cuenca", fontsize=10, fontweight="bold")
            ax.set_xlabel("Longitud (WGS84)", fontsize=8)
            ax.set_ylabel("Latitud (WGS84)", fontsize=8)
            ax.grid(True, linestyle="--", alpha=0.4, linewidth=0.5)
            ax.tick_params(labelsize=7.5)

            fig.tight_layout()
            fig.savefig(output_fig_path, dpi=200, bbox_inches="tight")
            plt.close(fig)
            return weights, str(output_fig_path)
        except Exception:
            return weights, None

    return weights, None
