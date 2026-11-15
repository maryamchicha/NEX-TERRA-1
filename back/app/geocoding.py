"""Reverse-geocode Moroccan coordinates to a nearby named locality."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

import requests

from .nasa.client import USER_AGENT

LOG = logging.getLogger("nex-terra.geocoding")

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"
CACHE_TTL_SECONDS = 86400
CACHE_MAX_ENTRIES = 512
REQUEST_INTERVAL_SECONDS = 1.05

_cache: "OrderedDict[Tuple[float, float], Tuple[float, Optional[Dict[str, str]]]]" = OrderedDict()
_lock = threading.Lock()
_last_request_at = 0.0


def reverse_geocode(lat: float, lon: float) -> Optional[Dict[str, str]]:
    """Return a named locality and its broader place context, if available."""
    global _last_request_at

    cache_key = (round(lat, 4), round(lon, 4))
    with _lock:
        now = time.monotonic()
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(cache_key)
            return cached[1]

        wait_seconds = REQUEST_INTERVAL_SECONDS - (now - _last_request_at)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            response = requests.get(
                NOMINATIM_REVERSE_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "zoom": 14,
                },
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "fr,en",
                },
                timeout=(3, 8),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            _last_request_at = time.monotonic()
            LOG.warning("OpenStreetMap locality lookup failed.")
            raise RuntimeError("Nearby locality lookup is temporarily unavailable.") from exc

        _last_request_at = time.monotonic()
        address = payload.get("address") if isinstance(payload, dict) else None
        result = _locality_from_address(address) if isinstance(address, dict) else None
        _cache[cache_key] = (time.monotonic(), result)
        _cache.move_to_end(cache_key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
        return result


def _locality_from_address(address: Dict[str, Any]) -> Optional[Dict[str, str]]:
    locality_fields = (
        "neighbourhood",
        "suburb",
        "quarter",
        "village",
        "hamlet",
        "town",
        "city",
        "municipality",
        "locality",
    )
    locality = next(
        (str(address[key]).strip() for key in locality_fields if address.get(key)),
        None,
    )
    if not locality:
        return None

    context_fields = ("city", "town", "municipality", "county")
    context = next(
        (
            str(address[key]).strip()
            for key in context_fields
            if address.get(key) and str(address[key]).strip() != locality
        ),
        None,
    )
    return {
        "place_name": locality,
        "context": context or "",
        "attribution_url": NOMINATIM_ATTRIBUTION_URL,
    }
