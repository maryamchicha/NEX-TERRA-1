"""Application configuration (Pydantic settings)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # NASA POWER endpoint proxy cache TTL (seconds)
    nasa_power_cache_ttl: int = 3600

    # Illustrative prototype climate scenarios; not validated regional projections.
    scenarios: list[dict] = Field(
        default=[
            {"id": "historical", "label": "Historical baseline",
             "temp_shift": 0.0, "precipitation": 1.0, "drought": 0.0},
            {"id": "mild_warming_wet", "label": "Mild warming + wetter",
             "temp_shift": 1.0, "precipitation": 1.05, "drought": 0.0},
            {"id": "severe_drying", "label": "Severe drying",
             "temp_shift": 1.8, "precipitation": 0.78, "drought": 0.35},
            {"id": "hot_wet", "label": "Hot + wet",
             "temp_shift": 2.2, "precipitation": 1.12, "drought": 0.10},
        ],
    )

    # default water cap per rotation (mm) used by the optimizer
    default_water_cap_mm: float = 1200.0
    optimization_water_cap_factor: float = 0.90

    class Config:
        env_file = ".env"
        extra = "ignore"


config = AppConfig()
