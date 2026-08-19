# HydroBasin

**HydroBasin** es una plataforma web para delimitación y análisis de cuencas hidrográficas a partir de Modelos Digitales de Elevación (DEM).

El proyecto separa la interfaz, la API y el motor geoespacial para que pueda crecer desde una herramienta de delimitación hacia una plataforma hidrológica completa.

## Arquitectura

```text
HydroBasin/
├── frontend/      # React + Vite + TypeScript
├── backend/       # FastAPI
├── engine/        # Motor hidrológico Python
└── README.md
```

## Flujo de análisis

```text
DEM
 ↓
Corrección hidrológica
 ↓
Dirección de flujo D8
 ↓
Acumulación de flujo
 ↓
Ajuste del punto de salida
 ↓
Delimitación de cuenca
 ├── Red de drenaje
 ├── Morfometría
 └── Exportaciones GIS
```

## Estado actual

La primera base incluye:

- interfaz web inicial orientada a proyectos;
- carga de DEM desde el navegador;
- selección de coordenadas del punto de salida;
- configuración del umbral de drenaje;
- API FastAPI;
- motor Python modular para DEM, flujo, cuenca y morfometría;
- endpoint de salud para verificar backend;
- endpoint preparado para ejecutar análisis reales.

## Desarrollo local

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

La API queda por defecto en `http://localhost:8000` y el frontend en `http://localhost:5173`.

## Roadmap

- mapa interactivo con selección visual del exutorio;
- renderización del DEM y resultados como capas web;
- orden de corrientes de Strahler;
- cauce principal;
- pendientes;
- curva hipsométrica;
- densidad de drenaje;
- tiempo de concentración;
- persistencia de proyectos;
- exportación GeoTIFF, GeoPackage y reportes.

## Nota

La implementación es propia y está inspirada en flujos hidrológicos estándar con Python. No reproduce de forma literal código propietario de cursos externos.
