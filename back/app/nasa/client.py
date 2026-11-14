"""NASA data adapters for the NEX TERRA prototype.

Endpoints used:
  * POWER    https://power.larc.nasa.gov (temp, humidity, radiation, precip)
  * GPM      IMERG precipitation (Earthdata / NOAA)
  * MODIS    EVI/NDVI monthly composites (NEON GDP API)
  * SMAP     surface soil moisture (USDA ShapDumps / NASA)
  * CMIP6    downscaled daily climate (NASA / CIESIN)

NASA POWER daily weather data are used for climate context and, when coverage
allows, FAO-56 reference evapotranspiration (ET0). Vegetation and future-climate
indicators remain synthetic placeholders; POWER values are gridded estimates,
not calibrated field measurements.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode

import requests

LOG = logging.getLogger("nex-terra.nasa")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
NASA_DIR = DATA_DIR / "nasa"

# NASA POWER public daily point endpoint.
POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMETERS = {
    "temp_mean_c": "T2M",
    "rainfall_mm_tot": "PRECTOTCORR",
    "sun_hours": "ALLSKY_SFC_SW_DWN",
    "humidity_pct": "RH2M",
}
ET0_POWER_PARAMETERS = (
    "T2M_MIN",
    "T2M_MAX",
    "RH2M",
    "WS2M",
    "ALLSKY_SFC_SW_DWN",
    "PS",
)
COMPOSITE_CACHE_VERSION = 3
POWER_MIN_COVERAGE = 0.95

# Experimental endpoint references; these are not currently used as data inputs.
GPM_COLLECTION = "GPM_L3_IMERG_MONTHLY_V06"
MODIS_COLLECTION = "MOD13A3_061"
SMAP_COLLECTION = "SMAP_L4_SM_fSAMPLE"
CMIP6_COLLECTION = "NEX-GDDP-CMIP6"
GPM_URL = f"https://imb.ext.nasa.gov/impacts/imerg/L3/IMERG_V06B_MONTHLY/{GPM_COLLECTION}"
MODIS_URL = f"https://modis-tropical.s3.amazonaws.com/{MODIS_COLLECTION}"
SMAP_URL = f"https://smap.jpl.nasa.gov/wp-content/uploads/2024/01/SMAP_L4_SM_fSAMPLE_{SMAP_COLLECTION}.json"
CMIP6_URL = f"https://ccui2.ess-wc.org/nex-gddp-cmip6/api/v1/cards/{CMIP6_COLLECTION}"

USER_AGENT = "nex-terra/1.0 (+agricultural decision-support)"
CACHE_TTL_SECONDS = 86400
RETRY_LIMIT = 3
BACKOFF = 1.5


class NasaConfig:
    """Metadata + URL construction for a single NASA collection."""

    def __init__(self, collection: str, lat: float, lon: float,
                 start_year: int, end_year: int, variable: str,
                 dataset: str | None = None, temporal: int = 2):
        self.collection = collection
        self.lat = lat
        self.lon = lon
        self.start_year = start_year
        self.end_year = end_year
        self.variable = variable
        self.dataset = dataset or collection
        self.temporal = temporal
        self.cache_path = NASA_DIR / (
            f"{self.collection}_{variable}_{lat:.5f}_{lon:.5f}_"
            f"{start_year}_{end_year}.json"
        )
        self.url = self._build_url()

    def _build_power_url(self) -> str:
        parameter = POWER_PARAMETERS.get(self.variable)
        if parameter is None:
            return ""
        params = {
            "parameters": parameter,
            "community": "AG",
            "longitude": f"{self.lon:.5f}",
            "latitude": f"{self.lat:.5f}",
            "start": f"{self.start_year}0101",
            "end": f"{self.end_year}1231",
            "format": "JSON",
            "time-standard": "UTC",
        }
        return f"{POWER_DAILY_URL}?{urlencode(params)}"

    def _build_gpm_url(self) -> str:
        return GPM_URL

    def _build_modis_url(self) -> str:
        return MODIS_URL

    def _build_smap_url(self) -> str:
        return SMAP_URL

    def _build_cmip6_url(self) -> str:
        return CMIP6_URL

    def _coalesce_url(self) -> str:
        if self.collection == "power":
            return self._build_power_url()
        if self.collection == "gpm":
            return self._build_gpm_url()
        if self.collection == "modis":
            return self._build_modis_url()
        if self.collection == "smap":
            return self._build_smap_url()
        if self.collection == "cmip6":
            return self._build_cmip6_url()
        return ""

    def _build_url(self) -> str:
        return self._coalesce_url()

    @property
    def cache_path(self) -> Path:
        return self._cache_path

    @cache_path.setter
    def cache_path(self, p: Path) -> None:
        self._cache_path = p


def _saturation_vapour_pressure(temp_c: float) -> float:
    return 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))


def _calculate_fao56_et0(
    day: date,
    t_max_c: float,
    t_min_c: float,
    actual_vapour_pressure_kpa: float,
    wind_speed_ms: float,
    solar_radiation_mj_m2_day: float,
    surface_pressure_kpa: float,
    latitude_deg: float,
    elevation_m: float,
) -> float:
    """Calculate daily grass-reference ET0 using the FAO-56 Penman-Monteith method."""
    t_mean_c = (t_max_c + t_min_c) / 2.0
    es = (
        _saturation_vapour_pressure(t_max_c)
        + _saturation_vapour_pressure(t_min_c)
    ) / 2.0
    delta = (
        4098.0 * _saturation_vapour_pressure(t_mean_c)
        / (t_mean_c + 237.3) ** 2
    )
    gamma = 0.000665 * surface_pressure_kpa

    day_angle = 2.0 * math.pi * day.timetuple().tm_yday / 365.0
    latitude = math.radians(latitude_deg)
    inverse_distance = 1.0 + 0.033 * math.cos(day_angle)
    solar_declination = 0.409 * math.sin(day_angle - 1.39)
    sunset_argument = max(
        -1.0,
        min(1.0, -math.tan(latitude) * math.tan(solar_declination)),
    )
    sunset_hour_angle = math.acos(sunset_argument)
    extraterrestrial_radiation = (
        (24.0 * 60.0 / math.pi)
        * 0.0820
        * inverse_distance
        * (
            sunset_hour_angle * math.sin(latitude) * math.sin(solar_declination)
            + math.cos(latitude)
            * math.cos(solar_declination)
            * math.sin(sunset_hour_angle)
        )
    )
    clear_sky_radiation = (
        0.75 + 2e-5 * elevation_m
    ) * extraterrestrial_radiation
    if clear_sky_radiation <= 0.0:
        raise ValueError("FAO-56 clear-sky radiation must be positive")

    cloudiness = max(
        0.3,
        min(1.0, solar_radiation_mj_m2_day / clear_sky_radiation),
    )
    net_shortwave = 0.77 * solar_radiation_mj_m2_day
    net_longwave = (
        4.903e-9
        * (
            ((t_max_c + 273.16) ** 4 + (t_min_c + 273.16) ** 4)
            / 2.0
        )
        * (0.34 - 0.14 * math.sqrt(max(0.0, actual_vapour_pressure_kpa)))
        * (1.35 * cloudiness - 0.35)
    )
    net_radiation = net_shortwave - net_longwave
    et0 = (
        0.408 * delta * net_radiation
        + gamma
        * (900.0 / (t_mean_c + 273.0))
        * wind_speed_ms
        * (es - actual_vapour_pressure_kpa)
    ) / (
        delta + gamma * (1.0 + 0.34 * wind_speed_ms)
    )
    return max(0.0, et0)


def _parse_power_daily_payload(
    payload: Dict[str, Any],
    start_date: date,
    end_date: date,
    latitude_deg: float,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("NASA POWER response must be a JSON object")
    properties = payload.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("NASA POWER response has invalid properties")
    parameters = properties.get("parameter", {})
    if not isinstance(parameters, dict):
        raise ValueError("NASA POWER response has no parameter series")

    header = payload.get("header", {})
    if not isinstance(header, dict):
        raise ValueError("NASA POWER response has invalid header")
    try:
        fill_value = float(header.get("fill_value", -999.0))
    except (TypeError, ValueError):
        fill_value = -999.0
    expected_days = (end_date - start_date).days + 1
    minimum_days = math.ceil(expected_days * POWER_MIN_COVERAGE)

    def read_series(
        parameter: str,
        *,
        required: bool = False,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> Dict[date, float]:
        raw_series = parameters.get(parameter)
        if not isinstance(raw_series, dict):
            if required:
                raise ValueError(f"NASA POWER response is missing {parameter}")
            return {}
        values = {}
        for day_key, raw_value in raw_series.items():
            try:
                day = datetime.strptime(day_key, "%Y%m%d").date()
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if day < start_date or day > end_date:
                continue
            if not math.isfinite(value) or value == fill_value:
                continue
            if minimum is not None and value < minimum:
                continue
            if maximum is not None and value > maximum:
                continue
            values[day] = value
        if required and len(values) < minimum_days:
            coverage = len(values) / expected_days
            raise ValueError(
                f"NASA POWER {parameter} coverage is {coverage:.1%}; "
                f"{POWER_MIN_COVERAGE:.0%} is required"
            )
        return values

    temperatures = read_series("T2M", required=True)
    precipitation = read_series("PRECTOTCORR", required=True, minimum=0.0)
    et0_inputs = {
        "T2M_MIN": read_series("T2M_MIN", minimum=-90.0, maximum=60.0),
        "T2M_MAX": read_series("T2M_MAX", minimum=-90.0, maximum=60.0),
        "RH2M": read_series("RH2M", minimum=0.0, maximum=100.0),
        "WS2M": read_series("WS2M", minimum=0.0),
        "ALLSKY_SFC_SW_DWN": read_series(
            "ALLSKY_SFC_SW_DWN", minimum=0.0
        ),
        "PS": read_series("PS", minimum=0.0, maximum=120.0),
    }
    et0_input_coverage = {
        key: round(len(values) / expected_days, 4)
        for key, values in et0_inputs.items()
    }

    elevation_m = None
    geometry = payload.get("geometry", {})
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, list) and len(coordinates) >= 3:
        try:
            candidate_elevation = float(coordinates[2])
            if math.isfinite(candidate_elevation) and -500.0 <= candidate_elevation <= 9000.0:
                elevation_m = candidate_elevation
        except (TypeError, ValueError):
            pass

    et0_by_day: Dict[date, float] = {}
    if elevation_m is not None:
        common_days = set.intersection(
            *(set(values) for values in et0_inputs.values())
        )
        for day in common_days:
            t_min = et0_inputs["T2M_MIN"][day]
            t_max = et0_inputs["T2M_MAX"][day]
            if t_min > t_max:
                continue
            es = (
                _saturation_vapour_pressure(t_max)
                + _saturation_vapour_pressure(t_min)
            ) / 2.0
            actual_vapour_pressure = (
                es * et0_inputs["RH2M"][day] / 100.0
            )
            et0_by_day[day] = _calculate_fao56_et0(
                day,
                t_max,
                t_min,
                actual_vapour_pressure,
                et0_inputs["WS2M"][day],
                et0_inputs["ALLSKY_SFC_SW_DWN"][day],
                et0_inputs["PS"][day],
                latitude_deg,
                elevation_m,
            )
    et0_coverage = len(et0_by_day) / expected_days
    et0_available = len(et0_by_day) >= minimum_days

    def covered_mean(values: Dict[date, float]) -> float | None:
        if len(values) < minimum_days:
            return None
        return round(sum(values.values()) / len(values), 2)

    months: Dict[str, Dict[str, float]] = {}
    for day, value in temperatures.items():
        month = day.strftime("%Y-%m")
        entry = months.setdefault(
            month,
            {
                "temp_total": 0.0,
                "temp_days": 0,
                "rain_total": 0.0,
                "et0_total": 0.0,
                "et0_days": 0,
            },
        )
        entry["temp_total"] += value
        entry["temp_days"] += 1
    for day, value in precipitation.items():
        month = day.strftime("%Y-%m")
        entry = months.setdefault(
            month,
            {
                "temp_total": 0.0,
                "temp_days": 0,
                "rain_total": 0.0,
                "et0_total": 0.0,
                "et0_days": 0,
            },
        )
        entry["rain_total"] += value
    for day, value in et0_by_day.items():
        month = day.strftime("%Y-%m")
        entry = months.setdefault(
            month,
            {
                "temp_total": 0.0,
                "temp_days": 0,
                "rain_total": 0.0,
                "et0_total": 0.0,
                "et0_days": 0,
            },
        )
        entry["et0_total"] += value
        entry["et0_days"] += 1

    series = {
        month: {
            "temp_mean_c": round(
                values["temp_total"] / values["temp_days"], 2
            ) if values["temp_days"] else None,
            "rainfall_mm": round(values["rain_total"], 2),
            "et0_mm": (
                round(values.get("et0_total", 0.0), 1)
                if et0_available
                and values.get("et0_days", 0)
                >= math.ceil(
                    monthrange(
                        int(month[:4]), int(month[5:7])
                    )[1] * POWER_MIN_COVERAGE
                )
                else None
            ),
        }
        for month, values in sorted(months.items())
    }
    sources = header.get("sources", [])
    api_info = header.get("api", {})
    if not isinstance(api_info, dict):
        api_info = {}
    return {
        "temp_mean_c": round(sum(temperatures.values()) / len(temperatures), 2),
        "rainfall_mm_tot": round(sum(precipitation.values()), 1),
        "series": series,
        "coverage": {
            "T2M": round(len(temperatures) / expected_days, 4),
            "PRECTOTCORR": round(len(precipitation) / expected_days, 4),
            **et0_input_coverage,
            "ET0": round(et0_coverage, 4),
        },
        "temp_min_mean_c": covered_mean(et0_inputs["T2M_MIN"]),
        "temp_max_mean_c": covered_mean(et0_inputs["T2M_MAX"]),
        "humidity_mean_pct": covered_mean(et0_inputs["RH2M"]),
        "wind_mean_ms": covered_mean(et0_inputs["WS2M"]),
        "solar_radiation_mean_mj_m2_day": covered_mean(
            et0_inputs["ALLSKY_SFC_SW_DWN"]
        ),
        "surface_pressure_mean_kpa": covered_mean(et0_inputs["PS"]),
        "et0_mean_mm_day": (
            round(sum(et0_by_day.values()) / len(et0_by_day), 2)
            if et0_available else None
        ),
        "et0_coverage_fraction": round(et0_coverage, 4),
        "et0_input_coverage": et0_input_coverage,
        "et0_reason": (
            None if et0_available
            else (
                "NASA POWER site elevation is unavailable"
                if elevation_m is None
                else "Complete daily FAO-56 input coverage is below 95%"
            )
        ),
        "elevation_m": elevation_m,
        "source_datasets": sources if isinstance(sources, list) else [],
        "api_version": api_info.get("version"),
        "time_standard": header.get("time_standard", "UTC"),
    }


def _fetch_power_daily(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
) -> Dict[str, Any]:
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValueError("NASA POWER coordinates are out of range")
    if start_year > end_year:
        raise ValueError("NASA POWER start year must not exceed end year")

    params = {
        "parameters": ",".join(
            ("T2M", "PRECTOTCORR", *ET0_POWER_PARAMETERS)
        ),
        "community": "AG",
        "longitude": f"{lon:.5f}",
        "latitude": f"{lat:.5f}",
        "start": f"{start_year}0101",
        "end": f"{end_year}1231",
        "format": "JSON",
        "time-standard": "UTC",
    }
    response = requests.get(
        POWER_DAILY_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=(5, 25),
    )
    response.raise_for_status()
    return _parse_power_daily_payload(
        response.json(),
        date(start_year, 1, 1),
        date(end_year, 12, 31),
        lat,
    )


def _composite_cache_path(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
) -> Path:
    return NASA_DIR / (
        f"composite_nasa_{lat:.5f}_{lon:.5f}_{start_year}_{end_year}.json"
    )


class NasaClient:
    """Per-collection client: cached, rate-limited, exported to JSON."""

    def __init__(self, config: NasaConfig, timeout: int = 60):
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # -- cache ---------------------------------------------------------- #
    def cache(self) -> Dict[str, Any]:
        p = self.config.cache_path
        try:
            if p.exists():
                age = time.time() - p.stat().st_mtime
                if age < CACHE_TTL_SECONDS:
                    with open(p, encoding="utf-8") as f:
                        return json.load(f)
                p.unlink()
        except (OSError, json.JSONDecodeError) as e:
            LOG.warning("nasa cache read failed %s: %s", p, e)
        return {}

    def store(self, payload: Dict[str, Any]) -> None:
        NASA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self.config.cache_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, self.config.cache_path)

    # -- main entry ----------------------------------------------------- #
    def fetch(self) -> Dict[str, Any]:
        cached = self.cache()
        if cached:
            LOG.info("nasa cached %s", self.config.collection)
            return cached
        # Fetch once; the public NASA endpoints for this demo are read-only and
        # frequently return 404 / rate-limit. Rather than burning 3 retries per
        # collection (up to ~5 collections = 15+ minutes of latency), we return
        # the deterministic synthetic series immediately so every API call
        # stays fast and the demo stays online.
        try:
            data = self._do_fetch(self.config.url)
            self.store(data)
            return data
        except requests.RequestException as e:
            LOG.warning(
                "nasa %s fetch failed (single attempt): %s",
                self.config.collection, e,
            )
        return self._synthetic()

    def _do_fetch(self, url: str) -> Dict[str, Any]:
        if not url:
            return self._synthetic()
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code == 200:
            return resp.json()
        LOG.warning("nasa %s HTTP %s %s", self.config.collection, resp.status_code, url)
        if resp.status_code in (200, 206):
            return self._parse_text(resp.text)
        raise requests.HTTPError(f"HTTP {resp.status_code} for {url}")

    def _synthetic(self) -> Dict[str, Any]:
        # Deterministic synthetic fallback used when live NASA fetches are
        # unreachable (offline / API rate-limited / no internet). The fallback
        # is a compact monthly series that the engine consumes directly, so the
        # demo keeps working at interactive speed without any live API call.
        series: Dict[str, Dict[str, float]] = {}
        for y in range(self.config.start_year, self.config.end_year + 1):
            base_temp = 16.5 + 0.04 * (y - 2019)
            for m in range(1, 13):
                key = f"{y}-{m:02d}"
                series[key] = {
                    "temp_mean_c": round(base_temp + 0.04 * (m - 6.5), 2),
                    "rainfall_mm": round(1.0 + 0.45 * (m in (10, 11, 12)), 2),
                    "sun_hours": round(5.2 + 0.6 * (m in (6, 7, 8)), 2),
                    "evi": round(0.35 + 0.05 * (m in (11, 12, 1)), 2),
                    "sm": round(0.22 + 0.10 * (m in (11, 12)), 2),
                    "humidity_pct": round(45 + 3 * (12 - m), 1),
                }
        return {
            "_synthetic": True,
            "synthetic_source": "fetch_nasa_series fallback",
            "series": series,
        }

    def _parse_text(self, text: str) -> Dict[str, Any]:
        return {"_raw": f"{len(text)} bytes",
                "_note": "NASA endpoint returned non-JSON; see engine-compatible series."}

    # -- public entry points (module-level) ------------------------------ #
    @staticmethod
    def fetch_nasa_series(lat: float, lon: float, start_year: int,
                          end_year: int) -> Dict[str, Any]:
        """Return NASA POWER climate data, derived reference ET0, and labeled placeholders."""
        lat, lon = float(lat), float(lon)
        cache_path = _composite_cache_path(lat, lon, start_year, end_year)
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                if (
                    isinstance(cached, dict)
                    and cached.get("_cache_version") == COMPOSITE_CACHE_VERSION
                    and cached.get("lat") == lat
                    and cached.get("lon") == lon
                    and cached.get("observed_window_years")
                    == [start_year, end_year]
                    and isinstance(cached.get("_cached_at"), (int, float))
                    and time.time() - cached["_cached_at"] < CACHE_TTL_SECONDS
                    and cached.get("data_status") in ("partial", "synthetic")
                    and isinstance(cached.get("source_status"), dict)
                    and isinstance(cached.get("temp_mean_c"), (int, float))
                    and isinstance(cached.get("rainfall_mm_tot"), (int, float))
                ):
                    return cached
            except (OSError, json.JSONDecodeError) as e:
                LOG.warning("NASA POWER cache read failed for %s: %s", cache_path, e)

        power_data = None
        power_error = None
        try:
            power_data = _fetch_power_daily(lat, lon, start_year, end_year)
        except (requests.RequestException, ValueError, TypeError) as exc:
            power_error = str(exc)
            LOG.warning(
                "NASA POWER daily data unavailable for %.5f,%.5f: %s",
                lat, lon, exc,
            )

        if power_data:
            dataset = ", ".join(power_data["source_datasets"]) or "NASA POWER"
            power_source = f"NASA POWER Daily API ({dataset})"
            weather_status = {
                "temp_mean_c": {
                    "status": "nasa_power",
                    "source": power_source,
                    "parameter": "T2M",
                    "units": "°C",
                    "coverage_fraction": power_data["coverage"]["T2M"],
                },
                "rainfall_mm_tot": {
                    "status": "nasa_power",
                    "source": power_source,
                    "parameter": "PRECTOTCORR",
                    "parameter_units": "mm/day",
                    "units": "mm over period",
                    "coverage_fraction": power_data["coverage"]["PRECTOTCORR"],
                },
            }
            for key, parameter, units in (
                ("humidity_pct", "RH2M", "%"),
                (
                    "solar_radiation_mj_m2_day",
                    "ALLSKY_SFC_SW_DWN",
                    "MJ/m²/day",
                ),
                ("temp_min_mean_c", "T2M_MIN", "°C"),
                ("temp_max_mean_c", "T2M_MAX", "°C"),
                ("wind_mean_ms", "WS2M", "m/s"),
                ("surface_pressure_mean_kpa", "PS", "kPa"),
            ):
                value_key = {
                    "humidity_pct": "humidity_mean_pct",
                    "solar_radiation_mj_m2_day":
                        "solar_radiation_mean_mj_m2_day",
                    "temp_min_mean_c": "temp_min_mean_c",
                    "temp_max_mean_c": "temp_max_mean_c",
                    "wind_mean_ms": "wind_mean_ms",
                    "surface_pressure_mean_kpa": "surface_pressure_mean_kpa",
                }[key]
                coverage = power_data["coverage"].get(parameter, 0.0)
                if power_data.get(value_key) is not None:
                    weather_status[key] = {
                        "status": "nasa_power",
                        "source": power_source,
                        "parameter": parameter,
                        "units": units,
                        "coverage_fraction": coverage,
                    }
                else:
                    weather_status[key] = {
                        "status": "unavailable",
                        "source": f"NASA POWER {parameter}",
                        "units": units,
                        "coverage_fraction": coverage,
                        "reason": "At least 95% daily coverage is required",
                    }
            et0_available = power_data["et0_mean_mm_day"] is not None
            weather_status["et0"] = {
                "status": "derived" if et0_available else "unavailable",
                "source": "FAO-56 Penman-Monteith reference ET0",
                "method": "Daily FAO-56 Penman-Monteith; mean RH2M vapor-pressure estimate",
                "units": "mm/day",
                "coverage_fraction": power_data["et0_coverage_fraction"],
                "input_coverage": power_data["et0_input_coverage"],
                "elevation_m": power_data["elevation_m"],
                **(
                    {}
                    if et0_available
                    else {"reason": power_data["et0_reason"]}
                ),
            }
            source_note = (
                "NASA POWER daily gridded estimates provide climate context. "
                "Reference ET0 is calculated with FAO-56 Penman-Monteith only "
                "when complete daily inputs meet the 95% coverage threshold; "
                "mean RH2M is used to estimate actual vapor pressure. These "
                "data do not calibrate the prototype score. Sunshine duration, "
                "EVI, soil moisture, and future climate remain placeholders."
            )
            data_status = "partial"
        else:
            weather_status = {
                "temp_mean_c": {
                    "status": "synthetic",
                    "source": "Prototype fallback",
                    "parameter": "T2M",
                    "units": "°C",
                    "reason": power_error,
                },
                "rainfall_mm_tot": {
                    "status": "synthetic",
                    "source": "Prototype fallback",
                    "parameter": "PRECTOTCORR",
                    "parameter_units": "mm/day",
                    "units": "mm over period",
                    "reason": power_error,
                },
                "et0": {
                    "status": "unavailable",
                    "source": "FAO-56 Penman-Monteith reference ET0",
                    "units": "mm/day",
                    "reason": "NASA POWER weather data are unavailable",
                },
            }
            source_note = (
                "NASA POWER data could not be retrieved or validated; "
                "temperature, precipitation, and other indicators are "
                "synthetic placeholders. No live values are used."
            )
            data_status = "synthetic"

        synthetic_fields = {
            "sun_hours": 5.0,
            "evi": 0.42,
            "sm": 0.30,
            "cmip6": {"temp_mean_c": 18.6, "precipitation_mm": 0.0},
        }
        humidity_pct = (
            power_data["humidity_mean_pct"]
            if power_data and power_data["humidity_mean_pct"] is not None
            else 45.0
        )
        solar_radiation = (
            power_data["solar_radiation_mean_mj_m2_day"]
            if power_data
            else None
        )
        synthetic_field_status = {
            key: {
                "status": "synthetic",
                "source": "Prototype placeholder",
            }
            for key in synthetic_fields
        }
        if not power_data or power_data["humidity_mean_pct"] is None:
            synthetic_field_status["humidity_pct"] = {
                "status": "synthetic",
                "source": "Prototype placeholder",
                **(
                    {"reason": "NASA POWER RH2M coverage is below 95%"}
                    if power_data else {}
                ),
            }
        source_status = {
            **weather_status,
            **synthetic_field_status,
        }
        payload = {
            "lat": lat,
            "lon": lon,
            "observed_window_years": [start_year, end_year],
            "temp_mean_c": power_data["temp_mean_c"] if power_data else 16.8,
            "rainfall_mm_tot": (
                power_data["rainfall_mm_tot"] if power_data else 0.0
            ),
            "temp_min_mean_c": (
                power_data["temp_min_mean_c"] if power_data else None
            ),
            "temp_max_mean_c": (
                power_data["temp_max_mean_c"] if power_data else None
            ),
            "humidity_pct": humidity_pct,
            "solar_radiation_mj_m2_day": solar_radiation,
            "wind_mean_ms": power_data["wind_mean_ms"] if power_data else None,
            "et0_mean_mm_day": (
                power_data["et0_mean_mm_day"] if power_data else None
            ),
            "elevation_m": power_data["elevation_m"] if power_data else None,
            **synthetic_fields,
            "series": power_data["series"] if power_data else {},
            "coverage": power_data["coverage"] if power_data else {},
            "source_status": source_status,
            "data_status": data_status,
            "_synthetic": any(
                item["status"] == "synthetic" for item in source_status.values()
            ),
            "source_note": source_note,
            "api_version": power_data["api_version"] if power_data else None,
            "time_standard": power_data["time_standard"] if power_data else None,
            "source_datasets": (
                power_data["source_datasets"] if power_data else []
            ),
            "_cache_version": COMPOSITE_CACHE_VERSION,
            "_cached_at": time.time(),
        }

        try:
            NASA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, cache_path)
        except OSError as e:
            LOG.warning("nasa composite cache write failed: %s", e)

        return payload

    # -- per-collection fetch shortcuts --------------------------------- #
    def power(self) -> Dict[str, Any]:
        return self.fetch()

    def gpm(self) -> Dict[str, Any]:
        return self.fetch()

    def modis(self) -> Dict[str, Any]:
        return self.fetch()

    def smap(self) -> Dict[str, Any]:
        return self.fetch()

    def cmip6(self) -> Dict[str, Any]:
        return self.fetch()

# ---- module-level convenience API ------------------------------------- #
def fetch_nasa_series(lat: float, lon: float, start_year: int,
                       end_year: int) -> Dict[str, Any]:
    return NasaClient.fetch_nasa_series(lat, lon, start_year, end_year)


def pull_demo_field_data(field: Dict[str, Any]) -> Dict[str, Any]:
    return NasaClient.fetch_nasa_series(
        float(field.get("lat", 32.75)), float(field.get("lon", -8.05)), 2019, 2024
    )
