from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "HydroBasin API"
    cors_origins: list[str] = ["http://localhost:5173"]
    workspace_dir: Path = Path("workspace")

    model_config = SettingsConfigDict(env_prefix="HYDROBASIN_", env_file=".env")


settings = Settings()
settings.workspace_dir.mkdir(parents=True, exist_ok=True)
