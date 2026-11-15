"""Pydantic request/response models for the NEX TERRA API."""

import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .crop_catalog import ROTATION_CROP_CODES
from .regions import MOROCCO_REGIONS, REGION_CODES, region_codes_for_point

DEFAULT_PRIORITY_WEIGHTS = {
    "water": 0.20,
    "nitrogen": 0.15,
    "resilience": 0.25,
    "soil": 0.20,
    "economy": 0.20,
}


# --------------------------------------------------------------------------- #
#  Request payloads
# --------------------------------------------------------------------------- #
class FieldUpdate(BaseModel):
    field_code: str
    lat: float
    lon: float
    region: str
    area_ha: float
    previous_crops: List[str] = Field(default_factory=list)
    irrigation: str = "rainfed"
    soil: Optional[Dict[str, Any]] = None

    @field_validator("lat")
    @classmethod
    def lat_in_range(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def lon_in_range(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180 and 180")
        return v


class RotationRequest(BaseModel):
    crops: List[str] = Field(default_factory=list, min_length=1, max_length=6)
    soil: Optional[Dict[str, Any]] = None
    climate: Optional[Dict[str, Any]] = None
    field: Optional["FarmField"] = None
    priorities: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_PRIORITY_WEIGHTS.copy()
    )

    @field_validator("crops")
    @classmethod
    def annual_rotation_crops_only(cls, value: List[str]) -> List[str]:
        invalid = sorted(set(value) - ROTATION_CROP_CODES)
        if invalid:
            raise ValueError(
                "Unknown or non-selectable crop code(s) for annual rotation: "
                f"{', '.join(invalid)}"
            )
        return value

    @field_validator("priorities")
    @classmethod
    def valid_priorities(cls, value: Dict[str, float]) -> Dict[str, float]:
        unknown = set(value) - set(DEFAULT_PRIORITY_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown priority keys: {', '.join(sorted(unknown))}")
        if any(not math.isfinite(weight) or weight < 0 for weight in value.values()):
            raise ValueError("Priority weights must be finite and non-negative")
        if not any(weight > 0 for weight in value.values()):
            raise ValueError("At least one priority weight must be greater than zero")
        return value


class ScenarioRequest(BaseModel):
    scenario_id: str = Field(default="default_scenario")


class FarmField(BaseModel):
    region_code: str
    lat: float = Field(ge=20.0, le=37.0)
    lon: float = Field(ge=-18.0, le=0.0)
    area_ha: float = Field(gt=0.0, le=100000.0)
    irrigation: str = "unknown"
    soil: Optional[Dict[str, Any]] = None

    @field_validator("region_code")
    @classmethod
    def known_region(cls, value: str) -> str:
        if value not in REGION_CODES:
            raise ValueError("Select one of Morocco's 12 administrative regions")
        return value

    @model_validator(mode="after")
    def region_matches_coordinates(self):
        matching_regions = region_codes_for_point(self.lat, self.lon)
        if self.region_code not in matching_regions:
            if matching_regions:
                region_names = {
                    region["code"]: region["name"]
                    for region in MOROCCO_REGIONS
                }
                matching_names = ", ".join(
                    region_names[code] for code in matching_regions
                )
                raise ValueError(
                    f"Coordinates fall within {matching_names}; select a matching region"
                )
            raise ValueError(
                "Coordinates do not fall within a mapped Moroccan administrative region"
            )
        return self

    @field_validator("irrigation")
    @classmethod
    def known_irrigation(cls, value: str) -> str:
        if value not in {"rainfed", "irrigated", "mixed", "unknown"}:
            raise ValueError("Irrigation must be rainfed, irrigated, mixed, or unknown")
        return value

    @field_validator("soil")
    @classmethod
    def valid_soil(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        allowed_types = {"sand", "loamy_sand", "loam", "silt_loam", "clay"}
        allowed_ranges = {
            "sand_pct": (0.0, 100.0),
            "silt_pct": (0.0, 100.0),
            "clay_pct": (0.0, 100.0),
            "ph": (0.0, 14.0),
            "organic_c_pct": (0.0, 100.0),
            "nacl_ppth": (0.0, 1000.0),
        }
        unknown = set(value) - set(allowed_ranges) - {"soil_type"}
        if unknown:
            raise ValueError(f"Unknown soil field(s): {', '.join(sorted(unknown))}")
        if "soil_type" in value and value["soil_type"] not in allowed_types:
            raise ValueError("Soil texture must be a supported texture or omitted")
        for key, (minimum, maximum) in allowed_ranges.items():
            if key not in value:
                continue
            number = value[key]
            if (
                isinstance(number, bool)
                or not isinstance(number, (int, float))
                or not math.isfinite(number)
                or number < minimum
                or number > maximum
            ):
                raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}")
        texture_fields = {"sand_pct", "silt_pct", "clay_pct"} & set(value)
        if texture_fields and texture_fields != {"sand_pct", "silt_pct", "clay_pct"}:
            raise ValueError("Enter sand, silt, and clay percentages together")
        if texture_fields and abs(
            sum(value[key] for key in texture_fields) - 100.0
        ) > 3.0:
            raise ValueError("Sand, silt, and clay percentages must total 100%")
        return value


class RotationRecommendationRequest(BaseModel):
    field: FarmField
    scenario_id: str = "historical"
    current_rotation: Optional[List[str]] = Field(
        default=None, min_length=3, max_length=3
    )
    priorities: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_PRIORITY_WEIGHTS.copy()
    )

    @field_validator("current_rotation")
    @classmethod
    def annual_current_rotation_only(
        cls, value: Optional[List[str]]
    ) -> Optional[List[str]]:
        if value is None:
            return value
        invalid = sorted(set(value) - ROTATION_CROP_CODES)
        if invalid:
            raise ValueError(
                "Unknown or non-selectable crop code(s) for annual rotation: "
                f"{', '.join(invalid)}"
            )
        return value

    @field_validator("priorities")
    @classmethod
    def valid_priorities(cls, value: Dict[str, float]) -> Dict[str, float]:
        unknown = set(value) - set(DEFAULT_PRIORITY_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown priority keys: {', '.join(sorted(unknown))}")
        if any(not math.isfinite(weight) or weight < 0 for weight in value.values()):
            raise ValueError("Priority weights must be finite and non-negative")
        if not any(weight > 0 for weight in value.values()):
            raise ValueError("At least one priority weight must be greater than zero")
        return value


# --------------------------------------------------------------------------- #
#  Response payloads
# --------------------------------------------------------------------------- #
class SeasonMetric(BaseModel):
    index: int
    crop: str
    water_mm: float
    n_balance_kg: float
    resilience: float
    soil_protection: float
    econom_inc: float


class RotationResult(BaseModel):
    id: str
    rotations: int
    rotation: List[str]
    name: Optional[str] = None
    water_total_mm: float
    water_avg_mm: float
    water_cap_factor: float
    n_balance_kg: float
    n_balance_per_season_kg: float
    resilience_avg: float
    soil_protection_avg: float
    economic_potential_avg: float
    econ_per_water_mad_m3: float
    score: float
    priority_weights: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_PRIORITY_WEIGHTS.copy()
    )
    scenarios: Dict[str, Any] = Field(default_factory=dict)
    seasons: List[SeasonMetric] = Field(default_factory=list)
    nasa: Dict[str, Any] = Field(default_factory=dict)
    field: Optional[FarmField] = None


class FieldResult(BaseModel):
    field_code: str
    name: str
    region: str
    lat: float
    lon: float
    area_ha: float
    terrain: str
    irrigation: str
    soil: Dict[str, Any]
    previous_crops: List[str]


class ScenariosResult(BaseModel):
    scenarios: List[Dict[str, Any]]


class ComparisonItem(BaseModel):
    id: str
    name: str
    rotation: List[str]
    water_total_mm: float
    n_balance_kg: float
    resilience_avg: float
    soil_protection_avg: float
    economic_potential_avg: float
    econ_per_water_mad_m3: float
    score: float


class OptimizationResult(BaseModel):
    optimized_rotation: List[str]
    score: Optional[float]
    n_evals: Optional[int]
    success: Optional[bool]


class ErrorResponse(BaseModel):
    detail: str
    code: int = 400


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _normalize_crops(crops: List[str]) -> List[str]:
    return [c.strip() for c in crops]


def _weather_label(sc: Dict[str, Any]) -> str:
    """Human readable label for a climate scenario."""
    ts = sc.get("temp_shift", 0.0)
    pd = sc.get("precipitation", 1.0)
    dr = sc.get("drought", 0.0)
    clover = ""
    if ts > 0:
        clover += f"+{ts:.1f}C"
    if 0 < pd < 1:
        clover += f" / {pd * 100:.0f}% rain"
    elif pd > 1:
        clover += f" +{(pd-1)*100:.0f}% rain"
    if dr > 0:
        clover += f" / drought {dr:.2f}"
    return clover or "baseline"


def _write_demo_field() -> FieldResult:
    """Write the virtual Settat field to the SQLite DB (mirrors a MAP layer)."""
    from .routes import _ensure_db
    return _ensure_db().get_field("SET-001")


# Rebuild all Pydantic models so ForwardRef annotations resolve after the model
# classes are fully defined. FastAPI's auto-body parsing wraps each request model
# in Annotated[ForwardRef(model), FieldInfo(...)] which requires a rebuild.
for _cls in (RotationRequest, FieldUpdate, ScenarioRequest, FarmField, SeasonMetric,
             RotationResult, FieldResult, ComparisonItem, ErrorResponse,
             OptimizationResult):
    _cls.model_rebuild(force=True)