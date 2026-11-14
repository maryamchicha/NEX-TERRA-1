"""Source-aware crop catalog and annual-rotation eligibility."""

import json
from pathlib import Path

from .regions import REGION_CODES

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "crop_catalog.json"


def _load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)

    source_ids = {source["id"] for source in catalog["sources"]}
    crop_codes = [crop["code"] for crop in catalog["crops"]]
    if len(crop_codes) != len(set(crop_codes)):
        raise ValueError("Crop catalog contains duplicate crop codes")
    for crop in catalog["crops"]:
        if not set(crop["source_ids"]).issubset(source_ids):
            raise ValueError(f"Crop {crop['code']} references an unknown source")
        if not set(crop["documented_regions"]).issubset(REGION_CODES):
            raise ValueError(f"Crop {crop['code']} references an unknown region")
        if crop["rotation_eligible"] and crop["life_cycle"] != "annual":
            raise ValueError(
                f"Only annual crops can be eligible for rotations: {crop['code']}"
            )
        if crop["rotation_eligible"] and crop["simulator_status"] != "prototype":
            raise ValueError(
                f"Rotation-eligible crop lacks prototype coefficients: {crop['code']}"
            )
    return catalog


CROP_CATALOG = _load_catalog()
ROTATION_CROP_CODES = frozenset(
    crop["code"] for crop in CROP_CATALOG["crops"] if crop["rotation_eligible"]
)
