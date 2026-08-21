from __future__ import annotations

from pathlib import Path
import pandas as pd
import geopandas as gpd

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_CORINE_CSV = DATA_DIR / "corine_to_scs.csv"


def load_corine_scs_table(csv_path: Path | None = None) -> pd.DataFrame:
    """Carga la tabla metodológica externa de equivalencias CORINE -> SCS."""
    path = csv_path or DEFAULT_CORINE_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró la tabla metodológica requerida: {path}. "
            "HydroBasin no utiliza equivalencias hardcodeadas en funciones."
        )

    df = pd.read_csv(path, dtype={"codigo_corine": str})
    df["codigo_corine"] = df["codigo_corine"].astype(str).str.strip()
    return df


def reclassify_landcover_scs(
    gdf_corine: gpd.GeoDataFrame, csv_path: Path | None = None
) -> gpd.GeoDataFrame:
    """Reclasifica las coberturas CORINE Land Cover a Uso del Suelo y Condición Hidrológica SCS."""
    if gdf_corine.empty:
        return gdf_corine

    lut = load_corine_scs_table(csv_path)
    # Crear diccionario de búsqueda directa por código string
    code_map = {}
    for _, r in lut.iterrows():
        code_map[str(r["codigo_corine"])] = {
            "uso_scs": str(r["uso_scs"]).strip(),
            "condicion_hidrologica": str(r["condicion_hidrologica"]).strip(),
            "descripcion_corine": str(r.get("descripcion_corine", "")).strip(),
        }

    gdf = gdf_corine.copy()

    usos = []
    condiciones = []
    descripciones = []
    unclassified_flags = []

    for _, row in gdf.iterrows():
        raw_code = row.get("codigo_corine")
        code_str = str(int(raw_code)) if pd.notnull(raw_code) else ""

        matched = None
        # 1. Búsqueda por código exacto
        if code_str in code_map:
            matched = code_map[code_str]
        # 2. Búsqueda por código Nivel 3 (primeros 3 dígitos)
        elif len(code_str) > 3 and code_str[:3] in code_map:
            matched = code_map[code_str[:3]]
        # 3. Búsqueda por código Nivel 2 (primeros 2 dígitos)
        elif len(code_str) > 2 and code_str[:2] in code_map:
            matched = code_map[code_str[:2]]
        # 4. Búsqueda por código Nivel 1 (primer dígito)
        elif len(code_str) > 1 and code_str[:1] in code_map:
            matched = code_map[code_str[:1]]

        if matched:
            usos.append(matched["uso_scs"])
            condiciones.append(matched["condicion_hidrologica"])
            descripciones.append(matched["descripcion_corine"] or row.get("leyenda") or "")
            unclassified_flags.append(False)
        else:
            usos.append(None)
            condiciones.append(None)
            descripciones.append(row.get("leyenda") or f"CORINE {code_str}")
            unclassified_flags.append(True)

    gdf["uso_scs"] = usos
    gdf["condicion_hidrologica"] = condiciones
    gdf["cobertura_nombre"] = descripciones
    gdf["corine_unclassified"] = unclassified_flags

    return gdf
