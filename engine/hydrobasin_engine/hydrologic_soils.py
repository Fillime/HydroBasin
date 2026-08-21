from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_LITHO_CSV = DATA_DIR / "lithology_to_hsg.csv"


def _normalize_str(text: str | None) -> str:
    if not text:
        return ""
    # Quitar tildes y caracteres especiales para matching de patrones
    norm = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in norm if not unicodedata.combining(c)).lower().strip()


def load_lithology_hsg_table(csv_path: Path | None = None) -> pd.DataFrame:
    """Carga la tabla metodológica externa de equivalencias Litología SGC -> Grupo Hidrológico (HSG)."""
    path = csv_path or DEFAULT_LITHO_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró la tabla metodológica requerida: {path}. "
            "HydroBasin no utiliza equivalencias geológicas hardcodeadas en funciones."
        )

    df = pd.read_csv(path)
    return df


def reclassify_geology_hsg(
    gdf_geology: gpd.GeoDataFrame, csv_path: Path | None = None
) -> gpd.GeoDataFrame:
    """Reclasifica las unidades geológicas y litologías del SGC a Grupos Hidrológicos de Suelo (A, B, C, D)
    aplicando la jerarquía estricta:
      1. Coincidencia exacta de SimboloUC.
      2. Regla metodológica explícita.
      3. Patrón litológico definido en CSV.
      4. Sin clasificación (None).
    """
    if gdf_geology.empty:
        return gdf_geology

    lut = load_lithology_hsg_table(csv_path)

    # 1. Mapa de SimboloUC exacto
    symbol_map = {}
    pattern_rules = []

    for _, r in lut.iterrows():
        sym = str(r["simbolo_uc"]).strip()
        pat = str(r.get("patron_litologico", "")).strip()
        hsg = str(r["grupo_hidrologico"]).strip().upper()
        crit = str(r.get("criterio_permeabilidad", "")).strip()

        if sym and sym != "*":
            symbol_map[sym.upper()] = (hsg, crit)
        elif pat:
            pattern_rules.append((_normalize_str(pat), hsg, crit))

    gdf = gdf_geology.copy()

    hsgs = []
    criterios = []
    unclassified_flags = []

    for _, row in gdf.iterrows():
        raw_sym = row.get("simbolo_uc")
        sym_upper = str(raw_sym).strip().upper() if pd.notnull(raw_sym) else ""
        desc_norm = _normalize_str(row.get("descripcion_geologica"))

        assigned_hsg = None
        assigned_crit = None

        # Prioridad 1: Coincidencia exacta de SimboloUC
        if sym_upper and sym_upper in symbol_map:
            assigned_hsg, assigned_crit = symbol_map[sym_upper]
        # Prioridad 2 y 3: Coincidencia por patrón litológico definido en CSV
        elif desc_norm:
            for pat_key, hsg_val, crit_val in pattern_rules:
                if pat_key in desc_norm:
                    assigned_hsg = hsg_val
                    assigned_crit = f"Coincidencia con patrón litológico CSV: '{pat_key}' ({crit_val})"
                    break

        if assigned_hsg in ["A", "B", "C", "D"]:
            hsgs.append(assigned_hsg)
            criterios.append(assigned_crit or "Regla metodológica SGC")
            unclassified_flags.append(False)
        else:
            hsgs.append(None)
            criterios.append("Sin clasificación en tabla metodológica")
            unclassified_flags.append(True)

    gdf["grupo_hidrologico"] = hsgs
    gdf["criterio_hsg"] = criterios
    gdf["hsg_unclassified"] = unclassified_flags

    return gdf
