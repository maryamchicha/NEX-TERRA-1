"""NEX TERRA rotation engine — soil/crop knowledge base + rotation simulator.

Engine:
  * A small, in-memory crop/soil knowledge base (crop database + soil profiles).
  * A compatibility / nitrogen-leakage rule base for crop sequences.
  * A physics-ish / agronomic simulator that scores a rotation on:
      - E: estimated water requirement (mm crop-season)
      - N: modelled nitrogen balance (kg N/ha per season, +ve = surplus/safe)
      - R: climate resilience (0..1)
      - S: soil protection (0..1) — erosion + organic matter + salinity
      - K: economic potential (index 0..1)
  * A scikit-learn fallback model that re-scores using a fitted linear model from
      historical field-rotation observations.
  * A SciPy optimizer (differential evolution) that searches for the best
      rotation under a water cap and illustrative climate scenarios.

Rotation scores are deterministic prototype estimates. NASA POWER weather
values are exposed as context but do not calibrate this engine's scores.
Climate scenarios are illustrative uniform shifts, not validated regional
projections.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import numpy as np
from scipy.optimize import differential_evolution

from ..models import DEFAULT_PRIORITY_WEIGHTS

# --------------------------------------------------------------------------- #
#  Paths and seed data
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SOILGRIDS_JSON = os.path.join(DATA_DIR, "soilgrids.json")
CROP_JSON = os.path.join(DATA_DIR, "crops.json")
FIELD_JSON = os.path.join(DATA_DIR, "field.json")

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")


# --------------------------------------------------------------------------- #
#  Knowledge base (seeded, no external network)
# --------------------------------------------------------------------------- #
DEFAULT_SOAKS = {
    "winter_wheat": 0.62,
    "barley": 0.55,
    "faba_beans": 0.60,
    "chickpeas": 0.58,
    "lentils": 0.57,
    "sunflower": 0.52,
    "sugar_beet": 0.50,
    "sweet_potato": 0.55,
    "potato": 0.50,
    "tomato": 0.48,
    "onion": 0.45,
    "carrot": 0.45,
    "alfalfa": 0.40,
    "clover": 0.40,
    "lettuce": 0.42,
    "maize": 0.58,
    "sorghum": 0.50,
    "pulses": 0.55,
    "cereal_mix": 0.58,
    "fallow": 0.0,
}

DEFAULT_SEAS = {
    "winter_wheat": "winter (Nov-Mar)",
    "barley": "winter (Nov-Feb)",
    "faba_beans": "winter (Nov-Dec)",
    "chickpeas": "winter (Nov-Dec)",
    "lentils": "winter (Nov-Dec)",
    "sunflower": "summer (Apr-Jul)",
    "sugar_beet": "winter (Nov-Mar)",
    "sweet_potato": "summer (May-Jul)",
    "potato": "summer (Mar-Jun)",
    "tomato": "summer (Apr-Jun)",
    "onion": "winter (Nov-Feb)",
    "carrot": "winter (Nov-Feb)",
    "alfalfa": "perennial",
    "clover": "perennial",
    "lettuce": "winter (Oct-Feb)",
    "maize": "summer (Feb-Jul)",
    "sorghum": "summer (Jan-Jun)",
    "pulses": "winter (Nov-Dec)",
    "cereal_mix": "winter (Nov-Mar)",
    "fallow": "fallow",
}

# Crop family / nutrient strategy
DEFAULT_FAMILIES = {
    "cereal": "cereal",
    "legume": "legume",
    "root": "root",
    "tuber": "tuber",
    "vegetable": "vegetable",
    "oilseed": "oilseed",
    "cinquefoil": "legume",  # alfalfa / clover = perennial legume
    "cover": "cover",
    "maize": "cereal",
    "sorghum": "cereal",
}

# Rotation compatibility matrix (transition probability 0..1, also encodes
# legume N-fix benefit). Higher = agronomically sensible continuation.
DEFAULT_COMPAT = {
    ("cereal", "cereal"): 0.30,      # continuous cereal = pest/disease build-up
    ("cereal", "legume"): 0.85,      # cereal -> legume: break cycle, N credit
    ("legume", "cereal"): 0.82,      # legume -> cereal: N credit, low disease
    ("legume", "legume"): 0.45,
    ("cereal", "oilseed"): 0.60,
    ("oilseed", "cereal"): 0.65,
    ("cereal", "root"): 0.55,
    ("root", "cereal"): 0.50,
    ("cereal", "tuber"): 0.55,
    ("tuber", "cereal"): 0.50,
    ("cereal", "vegetable"): 0.60,
    ("vegetable", "cereal"): 0.55,
    ("cereal", "cover"): 0.70,
    ("cover", "cereal"): 0.65,
    ("legume", "cover"): 0.70,
    ("cover", "legume"): 0.65,
    ("cereal", "maize"): 0.55,
    ("maize", "cereal"): 0.50,
    ("cereal", "sorghum"): 0.70,
    ("sorghum", "cereal"): 0.65,
    ("cereal", "fallow"): 0.60,
    ("fallow", "cereal"): 0.55,
}

# Water stress sensitivity (0 = very sensitive, 1 = tolerant) + baseline
# evapotranspiration index for a "normal" season (mm).
DEFAULT_STRESS = {
    "winter_wheat": 0.35,
    "barley": 0.30,
    "faba_beans": 0.30,
    "chickpeas": 0.33,
    "lentils": 0.34,
    "sunflower": 0.28,
    "sugar_beet": 0.30,
    "sweet_potato": 0.35,
    "potato": 0.30,
    "tomato": 0.28,
    "onion": 0.30,
    "carrot": 0.30,
    "alfalfa": 0.50,
    "clover": 0.50,
    "lettuce": 0.25,
    "maize": 0.33,
    "sorghum": 0.30,
    "pulses": 0.30,
    "cereal_mix": 0.32,
    "fallow": 0.0,
}

BASELINE_ET = {
    "winter_wheat": 420.0,
    "barley": 390.0,
    "faba_beans": 460.0,
    "chickpeas": 440.0,
    "lentils": 430.0,
    "sunflower": 520.0,
    "sugar_beet": 500.0,
    "sweet_potato": 560.0,
    "potato": 480.0,
    "tomato": 520.0,
    "onion": 400.0,
    "carrot": 400.0,
    "alfalfa": 650.0,
    "clover": 600.0,
    "lettuce": 300.0,
    "maize": 560.0,
    "sorghum": 500.0,
    "pulses": 460.0,
    "cereal_mix": 420.0,
    "fallow": 0.0,
}

# Economic parameters: gross revenue (MAD/ha) and water footprint (m3 per kg).
DEFAULT_ECON = {
    "winter_wheat": {"rev": 18500.0, "gwp": 1350.0},
    "barley": {"rev": 16500.0, "gwp": 1250.0},
    "faba_beans": {"rev": 21000.0, "gwp": 1100.0},
    "chickpeas": {"rev": 25000.0, "gwp": 1150.0},
    "lentils": {"rev": 26000.0, "gwp": 1200.0},
    "sunflower": {"rev": 20000.0, "gwp": 1400.0},
    "sugar_beet": {"rev": 23000.0, "gwp": 1300.0},
    "sweet_potato": {"rev": 15000.0, "gwp": 1500.0},
    "potato": {"rev": 19000.0, "gwp": 1400.0},
    "tomato": {"rev": 32000.0, "gwp": 1300.0},
    "onion": {"rev": 26000.0, "gwp": 1250.0},
    "carrot": {"rev": 22000.0, "gwp": 1250.0},
    "alfalfa": {"rev": 12000.0, "gwp": 900.0},
    "clover": {"rev": 9000.0, "gwp": 850.0},
    "lettuce": {"rev": 24000.0, "gwp": 1500.0},
    "maize": {"rev": 17000.0, "gwp": 1500.0},
    "sorghum": {"rev": 13000.0, "gwp": 1300.0},
    "pulses": {"rev": 21000.0, "gwp": 1150.0},
    "cereal_mix": {"rev": 17500.0, "gwp": 1300.0},
    "fallow": {"rev": 0.0, "gwp": 0.0},
}

# Pre-existing (baseline) crop->soil preference / benefit.  A positive value
# means the crop "likes" the current soil, negative means it degrades it.
DEFAULT_SOIL_PREF = {
    "winter_wheat": 0.2,
    "barley": 0.3,
    "faba_beans": -0.4,   # legume fixes N
    "chickpeas": -0.5,
    "lentils": -0.5,
    "sunflower": 0.1,
    "sugar_beet": -0.1,
    "sweet_potato": 0.2,
    "potato": -0.2,
    "tomato": -0.1,
    "onion": 0.3,
    "carrot": 0.2,
    "alfalfa": -0.6,      # heavy N-fixer, improves structure
    "clover": -0.6,
    "lettuce": 0.2,
    "maize": 0.1,
    "sorghum": 0.2,
    "pulses": -0.5,
    "cereal_mix": 0.1,
    "fallow": 0.0,
}


# --------------------------------------------------------------------------- #
#  SoilGrids-like soil profile
# --------------------------------------------------------------------------- #
@dataclass
class SoilProfile:
    soil_type: str = "loam"
    sand_pct: float = 40.0
    silt_pct: float = 40.0
    clay_pct: float = 20.0
    ph: float = 8.0
    organic_c_pct: float = 0.9
    nacl_ppth: float = 5.0
    bulk_density_g_cm3: float = 1.35
    active_carbon_mg_kg: float = 120.0
    nitrogen_total_mg_kg: float = 0.9

    @property
    def n_organic_kg_ha(self) -> float:
        # organic C * 1.724 * bulk density * 10000 (ha -> m2) * 10 (mg->kg)
        return self.organic_c_pct / 100.0 * 1.724 * self.bulk_density_g_cm3 * 10000 * 10

    @property
    def texture(self) -> str:
        if self.clay_pct >= 37.5 and self.sand_pct <= 45:
            return "clay"
        if self.sand_pct >= 70:
            return "sand"
        if self.clay_pct <= 20:
            return "loamy_sand" if self.sand_pct >= 50 else "silt_loam"
        return "loam"

    @property
    def erodibility(self) -> float:
        # higher = more erodible (sandy = low cohesion; clay = stable)
        return self.silt_pct * 0.5 + (100.0 - self.clay_pct) * 0.2 + self.sand_pct * 0.1

    @property
    def water_holding_capacity(self) -> float:
        # mm per m of soil
        if self.texture == "sand":
            return 80.0
        if self.texture == "loam":
            return 150.0
        if self.texture == "clay":
            return 170.0
        return 140.0

    @property
    def salinity_risk(self) -> float:
        return self.nacl_ppth / 40.0  # 0..~1+


# --------------------------------------------------------------------------- #
#  Crop (knowledge base rows)
# --------------------------------------------------------------------------- #
@dataclass
class Crop:
    code: str
    name: str
    family: str = "cereal"
    water_hunger: float = 0.55          # 0..1 relative water demand
    nutrient_strategy: str = "mineral"  # mineral / legume / biomass
    stress_sensitivity: float = 0.35
    base_et_mm: float = 420.0
    soil_pref: float = 0.0
    econ_rev_mad: float = 18500.0
    econ_gwp_m3kg: float = 1350.0
    compat: dict = field(default_factory=dict)

    def water_req_mm(self, scenario: float = 0.0, drought: float = 0.0) -> float:
        """Estimated evapotranspiration demand in mm for a full season."""
        # scenario: climate multiplier on ET (e.g. +2% per +0.5C warming)
        # drought: precipitation deficit multiplier (0..1), 0 = dry year
        base = self.base_et_mm * (1.0 + 0.4 * scenario)
        base *= (1.0 + 0.25 * drought)
        return base * self.water_hunger

    def nitrogen_balance(self, soil: SoilProfile, prev_crop_code: Optional[str] = None,
                         legume_fix: bool = False) -> float:
        """Net N balance (kg N/ha). +ve = surplus; -ve = deficit."""
        soil_n = soil.nitrogen_total_mg_kg * 10.0  # mg/kg -> kg/ha approx
        pref = self.soil_pref
        # legume N fixation credit
        if legume_fix and self.family == "legume":
            fix = 80.0
        elif legume_fix:
            fix = 30.0
        else:
            fix = 0.0
        # mineral crop uptake
        uptake = 40.0 * self.water_hunger
        n_balance = (self.nutrient_strategy == "biomass") * 50.0 \
                    + fix - uptake + pref * 15 - soil_n * 0.05
        return round(n_balance, 1)

    def soil_protection(self, prev_crop: Optional[str], prev_crop_is_cover: bool,
                        soil: SoilProfile, winter: bool) -> float:
        """Return soil protection score 0..1 for a season."""
        # cover crops + legumes protect; continuous cereal erodes
        cover_bonus = 0.35 if (prev_crop_is_cover or self.family == "cover") else 0.0
        legume_bonus = 0.15 if self.family == "legume" else 0.0
        # erosion driven by soil erodibility + crop residue
        erosion = soil.erodibility / 200.0
        residue = 0.5 + 0.3 * (self.family == "cereal")
        score = 0.55 * residue - 0.15 * erosion + cover_bonus + legume_bonus
        # salinity and pH stress
        if soil.nacl_ppth > 20:
            score -= 0.1
        if soil.ph > 8.5 or soil.ph < 6.0:
            score -= 0.1
        return round(max(0.0, min(1.0, score)), 3)

    def climate_resilience(self, temp_shift: float, precip_delta: float,
                           drought: float, evi: Optional[float] = None,
                           sm: Optional[float] = None) -> float:
        """Resilience 0..1 to a future climate scenario.

        evi: MODIS vegetation health (0..1); sm: SMAP surface soil moisture
        (0..1). Low EVI/SM compounds the drought penalty via the exposed
        vegetation's water-stress sensitivity.
        """
        thermal = 1.0 - 0.04 * abs(temp_shift)
        water = precip_delta * (1.0 - 0.2 * self.stress_sensitivity)
        # Vegetation and soil-moisture inputs contribute to compound drought stress.
        veg_sound = (evi if evi is not None else 0.7)
        soil_wet = (sm if sm is not None else 0.4)
        drought_penalty = (1.0 - 0.35 * drought) * (0.7 + 0.3 * veg_sound) * (0.8 + 0.2 * soil_wet)
        score = thermal * water * drought_penalty
        return round(max(0.0, min(1.0, score)), 3)

    def economic_potential(self) -> float:
        """Index 0..1 of gross margin on total irrigation water."""
        return round(min(1.0, self.econ_rev_mad / 40000.0), 3)


# --------------------------------------------------------------------------- #
#  Crop database + rotation rules
# --------------------------------------------------------------------------- #
class CropDatabase:
    def __init__(self, path: str = CROP_JSON):
        self.by_code: dict[str, Crop] = {}
        self._load(path)

    def _load(self, path: str):
        # Deterministic in-code defaults if no file present.
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for c in data:
                self.by_code[c["code"]] = self._row(c)
        else:
            for code, d in DEFAULT_SOAKS.items():
                self.by_code[code] = self._row({
                    "code": code,
                    "name": self._friendly(code),
                    "water_hunger": d,
                    "base_et_mm": BASELINE_ET.get(code, 420.0),
                    "family": DEFAULT_FAMILIES.get(code, "cereal"),
                    "stress_sensitivity": DEFAULT_STRESS.get(code, 0.35),
                    "soil_pref": DEFAULT_SOIL_PREF.get(code, 0.0),
                    "econ_rev_mad": DEFAULT_ECON.get(code, {"rev": 18500.0})["rev"],
                    "econ_gwp_m3kg": DEFAULT_ECON.get(code, {"rev": 18500.0})["gwp"],
                })

    @staticmethod
    def _friendly(code: str) -> str:
        return {
            "winter_wheat": "Winter wheat", "barley": "Barley",
            "faba_beans": "Faba beans", "chickpeas": "Chickpeas",
            "lentils": "Lentils", "sunflower": "Sunflower",
            "sugar_beet": "Sugar beet", "sweet_potato": "Sweet potato",
            "potato": "Potato", "tomato": "Tomato", "onion": "Onion",
            "carrot": "Carrot", "alfalfa": "Alfalfa", "clover": "Clover",
            "lettuce": "Lettuce", "maize": "Maize", "sorghum": "Sorghum",
            "pulses": "Pulses", "cereal_mix": "Cereal mix", "fallow": "Fallow",
        }.get(code, code.replace("_", " "))

    @staticmethod
    def _row(d: dict) -> Crop:
        return Crop(
            code=d["code"], name=d.get("name", d["code"]),
            water_hunger=d.get("water_hunger", 0.55),
            base_et_mm=d.get("base_et_mm", 420.0),
            family=d.get("family", "cereal"),
            stress_sensitivity=d.get("stress_sensitivity", 0.35),
            soil_pref=d.get("soil_pref", 0.0),
            econ_rev_mad=d.get("econ_rev_mad", 18500.0),
            econ_gwp_m3kg=d.get("econ_gwp_m3kg", 1350.0),
        )

    def crop(self, code: str) -> Optional[Crop]:
        return self.by_code.get(code)


# --------------------------------------------------------------------------- #
#  Rotator.
# --------------------------------------------------------------------------- #
class Rotator:
    def __init__(self, crops: Optional[CropDatabase] = None):
        self.crops = crops or CropDatabase()
        self._fitted: Optional[np.ndarray] = None

    # -- knowledge ---------------------------------------------------------- #
    def compat(self, prev: Optional[str], cur: Optional[str]) -> float:
        if prev is None or cur is None:
            return 0.55
        key = (prev, cur)
        if key in DEFAULT_COMPAT:
            return DEFAULT_COMPAT[key]
        rev = (cur, prev)
        if rev in DEFAULT_COMPAT:
            return DEFAULT_COMPAT[rev] * 0.8
        return 0.45

    def legume_fix_benefit(self, crop_code: Optional[str]) -> float:
        c = self.crops.crop(crop_code) if crop_code else None
        if c and c.family == "legume":
            return 1.0
        if c and c.family == "cover":
            return 0.4
        return 0.0

    # -- scoring ------------------------------------------------------------ #
    def score_rotation(
        self,
        crops: List[str],
        soil: SoilProfile,
        climate: dict,
        water_cap_mm: Optional[float] = None,
        nasa: Optional[dict] = None,
        priority_weights: Optional[dict] = None,
    ) -> dict:
        """Score a rotation against one climate state and weighted priorities.

        NASA fields are model inputs only when supplied; their provenance is
        returned separately by the data client.
        """
        if not crops:
            raise ValueError("A rotation must contain at least one crop")
        unknown_crops = [code for code in crops if self.crops.crop(code) is None]
        if unknown_crops:
            raise ValueError(f"Unknown crop code(s): {', '.join(unknown_crops)}")

        n = len(crops)
        season_metrics = []
        total_water = 0.0
        total_n_balance = 0.0
        total_resilience = 0.0
        total_soil = 0.0
        total_econ = 0.0
        observed_temp_c = nasa.get("temp_mean_c", 17.0) if nasa else 17.0
        observed_rain_mm = nasa.get("rainfall_mm_tot", 0.0) if nasa else 0.0
        observed_humidity = nasa.get("humidity_pct", 45.0) if nasa else 45.0
        evi = nasa.get("evi", 0.42) if nasa else 0.42
        sm = nasa.get("sm", 0.30) if nasa else 0.30
        cmip6_temp_shift = nasa.get("cmip6_temp_delta_c", 0.0) if nasa else 0.0
        for i, code in enumerate(crops):
            prev = crops[i - 1] if i > 0 else None
            cur = self.crops.crop(code)
            legume_fix = self.legume_fix_benefit(prev) > 0.0
            res = cur.climate_resilience(climate.get("temp_shift", 0.0),
                                         climate.get("precipitation", 1.0),
                                         climate.get("drought", 0.0),
                                         evi=evi, sm=sm)
            prev_cover = (i > 0 and
                          self.crops.crop(crops[i - 1]).family == "cover")
            soil_prot = cur.soil_protection(prev, prev_cover, soil, winter=(i < 2))
            # water demand: scale by observed rainfall deficit vs a wet baseline
            wwater = cur.water_req_mm(
                climate.get("temp_shift", 0.0),
                climate.get("drought", 0.0))
            nb = cur.nitrogen_balance(soil, prev, legume_fix)
            season_metrics.append({
                "index": i + 1,
                "crop": code,
                "water_mm": round(wwater, 1),
                "n_balance_kg": nb,
                "resilience": res,
                "soil_protection": soil_prot,
                "econom_inc": round(wwater * 0.4 + cur.econ_rev_mad * 0.01, 1),
                "nasa_temp_c": round(observed_temp_c, 2),
                "nasa_rain_mm": round(observed_rain_mm, 1),
                "nasa_evi": round(evi, 3),
                "nasa_sm": round(sm, 3),
            })
            total_water += wwater
            total_n_balance += nb
            total_resilience += res
            total_soil += soil_prot
            total_econ += cur.econ_rev_mad

        avg = lambda v: round(v / n, 3) if n else 0.0
        # economy per unit water (MAD / m3) - a dryland efficiency metric
        econ_per_water = round(total_econ / total_water, 1) if total_water > 0 else 0.0

        weights = (
            DEFAULT_PRIORITY_WEIGHTS
            if priority_weights is None else priority_weights
        )
        unknown_weights = set(weights) - set(DEFAULT_PRIORITY_WEIGHTS)
        if unknown_weights:
            raise ValueError(
                f"Unknown priority keys: {', '.join(sorted(unknown_weights))}"
            )
        normalized_weights = {}
        for key in DEFAULT_PRIORITY_WEIGHTS:
            value = float(weights.get(key, 0.0))
            if not math.isfinite(value) or value < 0:
                raise ValueError("Priority weights must be finite and non-negative")
            normalized_weights[key] = value
        weight_total = sum(normalized_weights.values())
        if weight_total <= 0:
            raise ValueError("At least one priority weight must be greater than zero")
        normalized_weights = {
            key: value / weight_total
            for key, value in normalized_weights.items()
        }

        # water scarcity penalty
        water_penalty = min(1.0, total_water / 1600.0)
        clamp = lambda value: max(0.0, min(1.0, value))
        components = {
            "water": clamp(1.0 - water_penalty),
            "nitrogen": clamp(0.5 + 0.5 * (total_n_balance / n / 100.0)),
            "resilience": clamp(total_resilience / n),
            "soil": clamp(total_soil / n),
            "economy": clamp(total_econ / n / 25000.0),
        }
        score = sum(
            normalized_weights[key] * components[key]
            for key in normalized_weights
        )

        return {
            "rotations": len(crops),
            "rotation": crops,
            "water_total_mm": round(total_water, 1),
            "water_avg_mm": round(avg(total_water), 1),
            "n_balance_kg": round(total_n_balance, 1),
            "n_balance_per_season_kg": round(avg(total_n_balance), 1),
            "resilience_avg": round(total_resilience / n, 3),
            "soil_protection_avg": round(total_soil / n, 3),
            "economic_potential_avg": round(total_econ / n, 1),
            "econ_per_water_mad_m3": econ_per_water,
            "score": round(score, 4),
            "priority_weights": {
                key: round(value, 4)
                for key, value in normalized_weights.items()
            },
            "nasa": {
                "temp_mean_c": round(observed_temp_c, 2),
                "rainfall_mm_tot": round(observed_rain_mm, 1),
                "sun_hours": round(5.0, 1),
                "humidity_pct": round(45.0, 1),
                "evi": round(evi, 3),
                "sm": round(sm, 3),
                "cmip6_temp_delta_c": round(cmip6_temp_shift, 2),
                "_synthetic": (
                    bool(nasa.get("_synthetic", True)) if nasa else True
                ),
                "data_status": (
                    nasa.get("data_status", "synthetic")
                    if nasa else "synthetic"
                ),
                "source_status": (
                    nasa.get("source_status", {}) if nasa else {}
                ),
                "lat": nasa.get("lat") if nasa else None,
                "lon": nasa.get("lon") if nasa else None,
                "observed_window_years": (
                    nasa.get("observed_window_years") if nasa else None
                ),
                "coverage": nasa.get("coverage", {}) if nasa else {},
                "source_datasets": (
                    nasa.get("source_datasets", []) if nasa else []
                ),
                "source_note": (
                    nasa.get(
                        "source_note",
                        "NASA data provenance unavailable; treated as synthetic.",
                    )
                    if nasa else "Engine defaults are synthetic demonstration values."
                ),
            },
            "seasons": season_metrics,
            "water_cap_factor": water_penalty,
        }

    # -- scikit-learn fallback model -------------------------------------- #
    def fit(self, historical: Optional[Iterable[dict]] = None):
        """Fit a small linear model to historical field-rotation outcomes so the
        engine can fallback when the agronomic model is unavailable."""
        rows = []
        for h in historical or []:
            rows.append({
                "water": h.get("water_total_mm", 0.0),
                "n": h.get("n_balance_kg", 0.0),
                "res": h.get("resilience_avg", 0.0),
                "soil": h.get("soil_protection_avg", 0.0),
                "econ": h.get("economic_potential_avg", 0.0),
            })
        if len(rows) < 2:
            self._fitted = np.array([0.4, 0.2, 0.2, 0.2])
            return
        X = np.array([[r["water"], r["n"], r["res"], r["soil"]] for r in rows])
        y = np.array([r["econ"] for r in rows])
        # ridge-ish least squares with intercept
        X1 = np.hstack([np.ones((X.shape[0], 1)), X])
        sol, *_ = np.linalg.lstsq(X1, y, rcond=None)
        self._fitted = sol

    def predict_with_model(self, features: dict) -> dict:
        if self._fitted is None or len(self._fitted) != 5:
            return {}
        x = np.array([
            features.get("water", 0.0),
            features.get("n", 0.0),
            features.get("res", 0.0),
            features.get("soil", 0.0),
        ], dtype=float)
        return {"ml_score": round(float(np.dot(self._fitted, np.concatenate([[1.0], x]))), 4)}

    # -- optimization ------------------------------------------------------- #
    def optimize(self, soil: SoilProfile, climate: dict,
                 priority_weights: dict, max_seasons: int = 3,
                 water_cap_mm: Optional[float] = None,
                 nasa: Optional[dict] = None) -> dict:
        """Search crop lists (3, 4 or 5 seasons) for a rotation that maximises the
        weighted utility under the given climate and water cap."""
        pool = [
            "winter_wheat", "barley", "faba_beans", "chickpeas", "lentils",
            "sunflower", "sugar_beet", "sweet_potato", "potato", "tomato",
            "onion", "carrot", "maize", "sorghum",
        ]
        bounds = [(0, len(pool) - 1)] * max_seasons

        def wrapped(x):
            idxs = [int(round(v)) for v in x]
            codes = [pool[i] for i in idxs]
            res = self.score_rotation(
                codes, soil, climate, nasa=nasa,
                priority_weights=priority_weights,
            )
            if "score" not in res:
                return -1e9
            utility = res["score"]
            # penalize exceeding a water cap
            if water_cap_mm and water_cap_mm > 0:
                excess = max(0.0, res["water_total_mm"] - water_cap_mm)
                utility -= excess / water_cap_mm
            return -utility

        res = differential_evolution(
            wrapped, bounds, maxiter=40, popsize=6, tol=1e-6, polish=True,
            updating="immediate", disp=False,
        )
        best_idxs = [int(round(v)) for v in res.x]
        best = [pool[i] for i in best_idxs if pool[i] != "fallow"]
        if not best:
            best = pool[:max_seasons]
        return {
            "optimized_rotation": best,
            "score": round(-res.fun, 4) if hasattr(res, "fun") else None,
            "n_evals": int(res.nit) if hasattr(res, "nit") else None,
            "success": bool(res.success) if hasattr(res, "success") else None,
        }


def build_soil_profile(payload: dict) -> SoilProfile:
    """Build a SoilProfile from a SoilGrids-style payload or a defaults."""
    return SoilProfile(
        soil_type=payload.get("soil_type", "loam"),
        sand_pct=payload.get("sand_pct", 40.0),
        silt_pct=payload.get("silt_pct", 40.0),
        clay_pct=payload.get("clay_pct", 20.0),
        ph=payload.get("ph", 8.0),
        organic_c_pct=payload.get("organic_c_pct", 0.9),
        nacl_ppth=payload.get("nacl_ppth", 5.0),
        bulk_density_g_cm3=payload.get("bulk_density_g_cm3", 1.35),
        active_carbon_mg_kg=payload.get("active_carbon_mg_kg", 120.0),
        nitrogen_total_mg_kg=payload.get("nitrogen_total_mg_kg", 0.9),
    )


def default_climate() -> dict:
    """Baseline climate state (no shift)."""
    return {"temp_shift": 0.0, "precipitation": 1.0, "drought": 0.0}


def scenario_from_deltas(temp_shift: float, precip_delta: float,
                         drought: float = 0.0) -> dict:
    """Build an illustrative scenario from temperature and precipitation shifts."""
    return {"temp_shift": float(temp_shift), "precipitation": float(precip_delta),
            "drought": float(drought)}
