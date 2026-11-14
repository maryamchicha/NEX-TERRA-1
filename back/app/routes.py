"""NEX TERRA API routes."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from . import config as _cfg, models
from .crop_catalog import CROP_CATALOG
from .models import (ComparisonItem, ErrorResponse, FieldResult, FieldUpdate,
                     FarmField, RotationRequest, RotationResult, ScenariosResult,
                     OptimizationResult)
from .simulator import simulator as sim
from fastapi import Body
from .regions import (
    BOUNDARY_SOURCE,
    MOROCCO_REGIONS,
    REGIONS_SOURCE_URL,
    admin1_boundary_feature_collection,
    region_codes_for_point,
)

router = APIRouter(tags=["nex-terra"])

log = logging.getLogger("nex-terra")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIELD_JSON = DATA_DIR / "field.json"
CONFIG_JSON = DATA_DIR / "config.json"

# In-memory "database" of the virtual field layers (SQLite mirrors this).
_db = {"fields": {}, "rotations": []}


# --------------------------------------------------------------------------- #
#  Field + soil store
# --------------------------------------------------------------------------- #
def _load_field_json() -> Dict[str, Any]:
    if FIELD_JSON.exists():
        with open(FIELD_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _ensure_db():
    return _db


def _soil_default() -> Dict[str, Any]:
    try:
        with open(DATA_DIR / "soilgrids.json", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if k != "field_code"}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _build_soil_profile(soil: Optional[Dict[str, Any]]) -> sim.SoilProfile:
    p = _soil_default()
    if soil:
        for k, v in soil.items():
            if k in p:
                p[k] = v
    return sim.build_soil_profile(p)


def _nasa_payload(lat: float, lon: float) -> Dict[str, Any]:
    """Return NASA POWER values for the farmer-selected field coordinates."""
    try:
        from app.nasa.client import fetch_nasa_series
        return fetch_nasa_series(lat, lon, 2019, 2024)
    except Exception as exc:  # noqa: BLE001 - keep the demo online no matter what
        log.warning("nasa payload unavailable: %s", exc)
        return {
            "temp_mean_c": 16.8,
            "rainfall_mm_tot": 0.0,
            "sun_hours": 5.0,
            "humidity_pct": 45.0,
            "temp_min_mean_c": None,
            "temp_max_mean_c": None,
            "solar_radiation_mj_m2_day": None,
            "wind_mean_ms": None,
            "et0_mean_mm_day": None,
            "elevation_m": None,
            "evi": 0.42,
            "sm": 0.30,
            "cmip6": {"temp_mean_c": 18.6, "precipitation_mm": 0.0},
            "lat": lat,
            "lon": lon,
            "observed_window_years": [2019, 2024],
            "coverage": {},
            "source_datasets": [],
            "data_status": "synthetic",
            "_synthetic": True,
            "source_status": {
                **{
                    key: {
                        "status": "synthetic",
                        "source": "Route fallback",
                    }
                    for key in (
                        "temp_mean_c", "rainfall_mm_tot", "sun_hours",
                        "humidity_pct", "evi", "sm", "cmip6",
                    )
                },
                **{
                    key: {
                        "status": "unavailable",
                        "source": "NASA POWER",
                        "reason": "NASA POWER weather data are unavailable",
                    }
                    for key in (
                        "temp_min_mean_c", "temp_max_mean_c",
                        "solar_radiation_mj_m2_day", "wind_mean_ms",
                        "surface_pressure_mean_kpa",
                    )
                },
                "et0": {
                    "status": "unavailable",
                    "source": "FAO-56 Penman-Monteith reference ET0",
                    "units": "mm/day",
                    "reason": "NASA POWER weather data are unavailable",
                },
            },
            "source_note": "Synthetic fallback values; no NASA POWER estimates are available.",
        }


def _default_climate() -> Dict[str, Any]:
    return {"temp_shift": 0.0, "precipitation": 1.0, "drought": 0.0}


def _require_field(payload: RotationRequest) -> FarmField:
    if payload.field is None:
        raise HTTPException(
            status_code=422,
            detail="Select a Moroccan field location before requesting a comparison",
        )
    return payload.field


# --------------------------------------------------------------------------- #
#  GET /api/field
# --------------------------------------------------------------------------- #
@router.get("/field", response_model=FieldResult)
def get_field():
    """Virtual field selection: returns the Settat demo field (the first/fixed
    'farmer selects their field' step)."""
    if not FIELD_JSON.exists():
        raise HTTPException(404, "No virtual field seed (data/field.json)")
    with open(FIELD_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    return FieldResult(
        field_code=raw.get("field_code", "SET-001"),
        name=raw.get("name", "Demo field"),
        region=raw.get("region", ""),
        lat=raw.get("lat", 32.75),
        lon=raw.get("lon", -8.05),
        area_ha=raw.get("area_ha", 10.0),
        terrain=raw.get("terrain", "flat"),
        irrigation=raw.get("irrigation", "rainfed"),
        soil=raw.get("soil", {}),
        previous_crops=raw.get("previous_crops", ["winter_wheat"]),
    )


@router.get("/regions")
def list_regions():
    """List Morocco's administrative regions and their boundary data source."""
    return {
        "regions": MOROCCO_REGIONS,
        "source": {
            "name": "Morocco Directorate General of Local Authorities",
            "url": REGIONS_SOURCE_URL,
            "note": (
                "The selected region is user-provided and checked against the "
                "mapped administrative boundary data."
            ),
        },
        "boundary_source": BOUNDARY_SOURCE,
    }


@router.get("/regions/locate")
def locate_region(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
):
    """Return mapped administrative regions covering a coordinate."""
    matching_codes = region_codes_for_point(lat, lon)
    if not matching_codes:
        raise HTTPException(
            status_code=422,
            detail=(
                "Coordinates do not fall within a mapped Moroccan "
                "administrative region"
            ),
        )
    matching_regions = [
        region for region in MOROCCO_REGIONS
        if region["code"] in matching_codes
    ]
    return {
        "region_codes": matching_codes,
        "regions": matching_regions,
        "boundary_source": BOUNDARY_SOURCE,
    }


@router.get("/regions/boundaries")
def get_region_boundaries():
    """Return simplified GeoJSON polygons for Morocco's 12 regions."""
    return admin1_boundary_feature_collection()


@router.get("/crops")
def list_crops():
    """Return crop life cycles, source provenance, and known regional evidence."""
    return CROP_CATALOG


# --------------------------------------------------------------------------- #
#  PUT /api/field
# --------------------------------------------------------------------------- #
@router.put("/field", response_model=FieldResult)
def update_field(payload: FieldUpdate):
    """Persist farmer field choices (location, previous crops, irrigation)."""
    cfg = _load_field_json()
    cfg.update({
        "field_code": payload.field_code,
        "lat": payload.lat,
        "lon": payload.lon,
        "region": payload.region,
        "area_ha": payload.area_ha,
        "terrain": payload.terrain,
        "irrigation": payload.irrigation,
        "previous_crops": list(payload.previous_crops),
        "soil": {},
    })
    with open(FIELD_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return FieldResult(
        field_code=payload.field_code,
        name="Custom field",
        region=payload.region,
        lat=payload.lat,
        lon=payload.lon,
        area_ha=payload.area_ha,
        terrain=payload.terrain,
        irrigation=payload.irrigation,
        soil={},
        previous_crops=list(payload.previous_crops),
    )


# --------------------------------------------------------------------------- #
#  GET /api/soil
# --------------------------------------------------------------------------- #
@router.get("/soil", responses={200: {"model": Dict[str, Any]}})
def get_soil():
    """Return the seeded demo soil profile; this is not a live SoilGrids query."""
    return _soil_default()


# --------------------------------------------------------------------------- #
#  GET /api/history
# --------------------------------------------------------------------------- #
@router.get("/history", response_model=List[Dict[str, Any]])
def get_history():
    """Past rotations for the field (pretend satellite/extension archive)."""
    # Deterministic demo history: plausible past 3 rotations for Settat.
    return [
        {"year": 2021, "rotation": ["winter_wheat", "winter_wheat"],
         "water_mm": 781.2, "n_kg": -66.6, "score": 0.597},
        {"year": 2022, "rotation": ["winter_wheat", "faba_beans", "winter_wheat"],
         "water_mm": 796.8, "n_kg": -74.8, "score": 0.600},
        {"year": 2023, "rotation": ["winter_wheat", "alfalfa", "sunflower"],
         "water_mm": 790.8, "n_kg": -67.4, "score": 0.574},
        {"year": 2024, "rotation": ["winter_wheat", "winter_wheat", "winter_wheat"],
         "water_mm": 781.2, "n_kg": -66.6, "score": 0.597},
        {"year": 2025, "rotation": ["winter_wheat", "faba_beans", "sunflower"],
         "water_mm": 805.1, "n_kg": -71.2, "score": 0.585},
    ]


# --------------------------------------------------------------------------- #
#  POST /api/simulate
# --------------------------------------------------------------------------- #
@router.post("/simulate", response_model=RotationResult)
def simulate(payload: RotationRequest):
    """Simulate one crop rotation under one climate state."""
    field = _require_field(payload)
    rotator = app_state_roator()
    soil = _build_soil_profile(field.soil or payload.soil)
    climate = payload.climate or _default_climate()
    nasa = _nasa_payload(field.lat, field.lon)

    # default demonstration rotation A / B / C
    crops = payload.crops or ["winter_wheat", "winter_wheat", "winter_wheat"]

    try:
        res = rotator.score_rotation(
            crops, soil, climate, nasa=nasa,
            priority_weights=payload.priorities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RotationResult(
        id=climate.get("id", "default"),
        rotations=res["rotations"],
        rotation=res["rotation"],
        name=models._weather_label(climate),
        water_total_mm=res["water_total_mm"],
        water_avg_mm=res["water_avg_mm"],
        water_cap_factor=res["water_cap_factor"],
        n_balance_kg=res["n_balance_kg"],
        n_balance_per_season_kg=res["n_balance_per_season_kg"],
        resilience_avg=res["resilience_avg"],
        soil_protection_avg=res["soil_protection_avg"],
        economic_potential_avg=res["economic_potential_avg"],
        econ_per_water_mad_m3=res["econ_per_water_mad_m3"],
        score=res["score"],
        priority_weights=res["priority_weights"],
        seasons=res["seasons"],
        nasa=res["nasa"],
        field=field,
    )


# --------------------------------------------------------------------------- #
#  GET /api/scenarios
# --------------------------------------------------------------------------- #
@router.get("/scenarios", response_model=ScenariosResult)
def list_scenarios():
    """Return illustrative climate scenarios for prototype stress testing."""
    return ScenariosResult(scenarios=_cfg.config.scenarios)


# --------------------------------------------------------------------------- #
#  POST /api/compare
# --------------------------------------------------------------------------- #
@router.post("/compare", response_model=Dict[str, Any])
def compare(payload: RotationRequest):
    """Compare the supplied rotation and two illustrative alternatives.

    Returns:
        - per-strategy metrics under each climate scenario
        - strategy ranking by mean weighted score across scenarios
        - the winner for each scenario
    """
    field = _require_field(payload)
    rotator = app_state_roator()
    soil = _build_soil_profile(field.soil or payload.soil)
    nasa = _nasa_payload(field.lat, field.lon)

    scenario_ids = [s.get("id", "default") for s in _cfg.config.scenarios]
    demo_rotation = payload.crops
    strategies = [
        {
            "id": "current",
            "label": "A. Current rotation (user input)",
            "rotation": demo_rotation,
            "rationale": "Reference sequence supplied for this comparison.",
            "limitations": [
                "The reference rotation is not independently validated.",
                "Model coefficients are demonstration assumptions.",
            ],
        },
        {
            "id": "cereal_legume",
            "label": "B. Cereal–legume rotation",
            "rotation": ["winter_wheat", "faba_beans", "winter_wheat"],
            "rationale": (
                "Introduces a legume; the engine applies a modeled nitrogen "
                "benefit, not a locally measured outcome."
            ),
            "limitations": [
                "Pest and disease cycles are not modeled.",
                "The nitrogen benefit is not validated for this field.",
            ],
        },
        {
            "id": "diversified",
            "label": "C. Cereal–legume–oilseed rotation",
            "rotation": ["barley", "chickpeas", "sunflower"],
            "rationale": (
                "Uses three crop families; the score does not account for "
                "local market access or pest cycles."
            ),
            "limitations": [
                "Market prices and input costs are not modeled.",
                "The sequence is illustrative, not a regional calendar.",
            ],
        },
    ]

    catalog_by_code = {
        crop["code"]: crop for crop in CROP_CATALOG["crops"]
    }
    for strategy in strategies:
        strategy["crop_evidence"] = [
            {
                "code": code,
                "name": catalog_by_code[code]["name"],
                "life_cycle": catalog_by_code[code]["life_cycle"],
                "national_status": catalog_by_code[code]["national_status"],
                "source_ids": catalog_by_code[code]["source_ids"],
                "documented_regions": catalog_by_code[code]["documented_regions"],
                "evidence_note": catalog_by_code[code]["evidence_note"],
            }
            for code in strategy["rotation"]
        ]
        unverified_crops = sorted({
            crop["name"] for crop in strategy["crop_evidence"]
            if crop["national_status"] != "documented"
        })
        region_unverified_crops = sorted({
            crop["name"] for crop in strategy["crop_evidence"]
            if field.region_code not in crop["documented_regions"]
        })
        strategy["data_gaps"] = []
        if unverified_crops:
            strategy["data_gaps"].append(
                "National crop-presence evidence is unverified or group-level "
                f"for: {', '.join(unverified_crops)}."
            )
        if region_unverified_crops:
            strategy["data_gaps"].append(
                "The cited sources do not document these crops in the selected "
                f"administrative region: {', '.join(region_unverified_crops)}. "
                "This is a data gap, not evidence of absence."
            )

    comparisons = []
    for sc in _cfg.config.scenarios:
        for strategy in strategies:
            try:
                sim_result = rotator.score_rotation(
                    strategy["rotation"], soil, sc, nasa=nasa,
                    priority_weights=payload.priorities,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            comparisons.append({
                "strategy_id": strategy["id"],
                "strategy_label": strategy["label"],
                "scenario_id": sc.get("id", "default"),
                "label": sc.get("label", "baseline"),
                "temp_shift": sc.get("temp_shift", 0.0),
                "precipitation": sc.get("precipitation", 1.0),
                "drought": sc.get("drought", 0.0),
                "rotation": list(sim_result["rotation"]),
                "water_total_mm": sim_result["water_total_mm"],
                "n_balance_kg": sim_result["n_balance_kg"],
                "resilience_avg": sim_result["resilience_avg"],
                "soil_protection_avg": sim_result["soil_protection_avg"],
                "economic_potential_avg": sim_result["economic_potential_avg"],
                "econ_per_water_mad_m3": sim_result["econ_per_water_mad_m3"],
                "score": sim_result["score"],
                "priority_weights": sim_result["priority_weights"],
            })

    ranked = _rank(comparisons)
    scenario_winners = []
    for scenario_id in scenario_ids:
        rows = [item for item in comparisons if item["scenario_id"] == scenario_id]
        if rows:
            winner = max(rows, key=lambda item: item["score"])
            scenario_winners.append({
                "scenario_id": scenario_id,
                "strategy_id": winner["strategy_id"],
                "strategy_label": winner["strategy_label"],
                "score": winner["score"],
            })

    return {
        "rotations": demo_rotation,
        "strategies": strategies,
        "rotation_names": {strategy["id"]: strategy["label"]
                           for strategy in strategies},
        "comparison": comparisons,
        "ranked": ranked,
        "scenario_winners": scenario_winners,
        "scenario_ids": scenario_ids,
        "scenarios": _cfg.config.scenarios,
        "comparison_context": {
            "score_status": "illustrative prototype heuristic",
            "field_soil_status": (
                "some user-provided soil information; unspecified properties "
                "use prototype defaults"
                if field.soil or payload.soil
                else "prototype defaults; not measured"
            ),
            "nasa_data_status": nasa.get("data_status", "synthetic"),
            "score_explanation": (
                "A weighted sum of five prototype components using the "
                "user-selected priority weights; the ranking is not a crop "
                "recommendation."
            ),
            "score_inputs": [
                "Prototype crop coefficients and water-demand assumptions.",
                (
                    "User-supplied soil measurements where present; otherwise "
                    "prototype default soil values."
                ),
                "Illustrative climate-scenario deltas and normalized priority weights.",
                (
                    "Synthetic vegetation and soil-moisture placeholders, "
                    "which affect the prototype resilience component."
                ),
            ],
            "nasa_role": (
                "NASA POWER weather and FAO-56 reference ET0 are shown as "
                "climate context; observed weather and ET0 do not calibrate "
                "the prototype crop coefficients or directly determine the "
                "rotation score."
            ),
            "data_gaps": [
                (
                    "No verified crop calendar or crop-specific suitability "
                    "layer is available for the selected administrative region."
                ),
                (
                    "Crop-stage water schedules and crop-specific Kc values "
                    "are not used to calculate the prototype water metric."
                ),
                "Pest and disease cycles are not modeled.",
                (
                    "The economic component uses prototype revenue assumptions; "
                    "market prices, input costs, and net margins are not modeled."
                ),
                "The scores have not been calibrated against farm outcomes.",
            ],
        },
        "nasa": nasa,
        "field": field.model_dump(),
    }


# --------------------------------------------------------------------------- #
#  POST /api/optimize
# --------------------------------------------------------------------------- #
@router.post("/optimize", response_model=OptimizationResult)
def optimize(request: Optional[RotationRequest] = None):
    """Search for the rotation that best satisfies the farmer's priorities
    (water, nitrogen, resilience, soil, economy) under a future climate
    scenario using SciPy differential evolution."""

    if request is None:
        raise HTTPException(
            status_code=422,
            detail="Select a Moroccan field location before optimizing a rotation",
        )
    field = _require_field(request)
    rotator = app_state_roator()
    soil = _build_soil_profile(field.soil or request.soil)
    climate = request and request.climate or _default_climate()

    priorities = (
        request.priorities if request
        else models.DEFAULT_PRIORITY_WEIGHTS.copy()
    )
    nasa = _nasa_payload(field.lat, field.lon)
    res = rotator.optimize(
        soil, climate, priorities, max_seasons=3,
        water_cap_mm=None, nasa=nasa,
    )
    return OptimizationResult(**res)


# --------------------------------------------------------------------------- #
#  Ranking & explanation helpers (pure logic)
# --------------------------------------------------------------------------- #
def _rank(comparisons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank strategies by mean weighted score over all climate scenarios."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in comparisons:
        grouped.setdefault(item["strategy_id"], []).append(item)

    ranked = []
    for strategy_id, rows in grouped.items():
        scores = [item["score"] for item in rows]
        ranked.append({
            "id": strategy_id,
            "label": rows[0]["strategy_label"],
            "rotation": rows[0]["rotation"],
            "average_score": round(sum(scores) / len(scores), 4),
            "worst_case_score": round(min(scores), 4),
            "water_mm": round(
                sum(item["water_total_mm"] for item in rows) / len(rows), 1
            ),
        })
    ranked.sort(key=lambda item: item["average_score"], reverse=True)
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item["score"] = item["average_score"]
    return ranked


# --------------------------------------------------------------------------- #
#  App state helpers
# --------------------------------------------------------------------------- #
def app_state_roator() -> sim.Rotator:
    """Pull the app-wide rotator from the FastAPI app state (avoids circular
    imports)."""
    from .main import app  # local import to avoid module loop
    return app.state.rotator


@router.get("/nasa")
def api_nasa(
    lat: float = Query(..., ge=20.0, le=37.0),
    lon: float = Query(..., ge=-18.0, le=0.0),
):
    """Return NASA values for a selected point within Morocco's broad envelope."""
    return _nasa_payload(lat, lon)


# --------------------------------------------------------------------------- #
#  Frontend! (serve demo assets)
# --------------------------------------------------------------------------- #
@router.get("/demo/seed.json", response_model=Dict[str, Any])
def demo_seed():
    """Return simulator defaults without assigning a farm location or climate."""
    return {
        "rotation_names": {
            "current": "A. Current rotation (user input)",
            "cereal_legume": "B. Cereal–legume rotation",
            "diversified": "C. Cereal–legume–oilseed rotation",
        },
        "current_rotation": ["winter_wheat", "winter_wheat", "winter_wheat"],
        "scenarios": _cfg.config.scenarios,
        "priorities": models.DEFAULT_PRIORITY_WEIGHTS.copy(),
    }
