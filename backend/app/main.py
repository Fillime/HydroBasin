from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.health import router as health_router
from app.api.routes.progress import router as progress_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="API geoespacial de HydroBasin para análisis de cuencas hidrográficas.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(progress_router, prefix="/api")
app.include_router(artifacts_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "HydroBasin API", "docs": "/docs"}
