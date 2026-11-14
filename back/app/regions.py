"""Morocco's 12 administrative regions used for farmer-selected field context."""

import json
import math
from functools import lru_cache
from pathlib import Path

MOROCCO_REGIONS = [
    {"code": "tanger-tetouan-al-hoceima", "name": "Tangier-Tetouan-Al Hoceima"},
    {"code": "oriental", "name": "Oriental"},
    {"code": "fes-meknes", "name": "Fes-Meknes"},
    {"code": "rabat-sale-kenitra", "name": "Rabat-Sale-Kenitra"},
    {"code": "beni-mellal-khenifra", "name": "Beni Mellal-Khenifra"},
    {"code": "casablanca-settat", "name": "Casablanca-Settat"},
    {"code": "marrakech-safi", "name": "Marrakech-Safi"},
    {"code": "draa-tafilalet", "name": "Draa-Tafilalet"},
    {"code": "souss-massa", "name": "Souss-Massa"},
    {"code": "guelmim-oued-noun", "name": "Guelmim-Oued Noun"},
    {"code": "laayoune-sakia-el-hamra", "name": "Laayoune-Sakia El Hamra"},
    {"code": "dakhla-oued-ed-dahab", "name": "Dakhla-Oued Ed-Dahab"},
]

REGION_CODES = {region["code"] for region in MOROCCO_REGIONS}
REGIONS_SOURCE_URL = "https://www.collectivites-territoriales.gov.ma/"

BOUNDARY_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "morocco_admin1_simplified.geojson"
)
BOUNDARY_SOURCE = {
    "name": "geoBoundaries GB Open Morocco ADM1",
    "year": 2017,
    "source": "OpenStreetMap, Wambacher",
    "url": (
        "https://github.com/wmgeolab/geoBoundaries/tree/9469f09/"
        "releaseData/gbOpen/MAR/ADM1"
    ),
    "license": "Open Data Commons Open Database License 1.0",
    "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
}

_REGION_CODE_BY_ISO = {
    "MA-01": "tanger-tetouan-al-hoceima",
    "MA-02": "oriental",
    "MA-03": "fes-meknes",
    "MA-04": "rabat-sale-kenitra",
    "MA-05": "beni-mellal-khenifra",
    "MA-06": "casablanca-settat",
    "MA-07": "marrakech-safi",
    "MA-08": "draa-tafilalet",
    "MA-09": "souss-massa",
    "MA-10": "guelmim-oued-noun",
    "MA-11": "laayoune-sakia-el-hamra",
    "MA-12": "dakhla-oued-ed-dahab",
}


@lru_cache(maxsize=1)
def _admin1_geometries():
    with BOUNDARY_DATA_PATH.open(encoding="utf-8") as boundary_file:
        boundary_data = json.load(boundary_file)
    if boundary_data.get("type") != "FeatureCollection":
        raise ValueError("Morocco boundary data must be a GeoJSON FeatureCollection")

    geometries = {}
    for feature in boundary_data.get("features", []):
        properties = feature.get("properties", {})
        region_code = _REGION_CODE_BY_ISO.get(properties.get("shapeISO"))
        geometry = feature.get("geometry")
        if region_code is None or not isinstance(geometry, dict):
            continue
        geometries[region_code] = geometry

    missing_regions = REGION_CODES - geometries.keys()
    if missing_regions:
        raise ValueError(
            "Morocco boundary data is missing region code(s): "
            + ", ".join(sorted(missing_regions))
        )
    return geometries


def admin1_boundary_feature_collection():
    """Return simplified region polygons labeled with app region codes."""
    geometries = _admin1_geometries()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "region_code": region["code"],
                    "region_name": region["name"],
                },
                "geometry": geometries[region["code"]],
            }
            for region in MOROCCO_REGIONS
        ],
    }


def _point_on_segment(lon, lat, start, end):
    x1, y1 = start[:2]
    x2, y2 = end[:2]
    tolerance = 1e-10
    cross = (lon - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
    if abs(cross) > tolerance:
        return False
    return (
        min(x1, x2) - tolerance <= lon <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= lat <= max(y1, y2) + tolerance
    )


def _point_on_ring(lon, lat, ring):
    return any(
        _point_on_segment(lon, lat, start, end)
        for start, end in zip(ring, ring[1:])
    )


def _ring_contains(lon, lat, ring):
    inside = False
    for start, end in zip(ring, ring[1:]):
        x1, y1 = start[:2]
        x2, y2 = end[:2]
        if _point_on_segment(lon, lat, start, end):
            return True
        if (y1 > lat) != (y2 > lat):
            crossing_lon = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < crossing_lon:
                inside = not inside
    return inside


def _polygon_contains(lon, lat, rings):
    if not rings or not _ring_contains(lon, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if _point_on_ring(lon, lat, hole):
            return True
        if _ring_contains(lon, lat, hole):
            return False
    return True


def region_codes_for_point(lat, lon):
    """Return all mapped administrative regions covering a coordinate."""
    if not math.isfinite(lat) or not math.isfinite(lon):
        return []

    geometries = _admin1_geometries()
    matches = set()
    for region_code, geometry in geometries.items():
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            polygons = coordinates
        else:
            raise ValueError(
                f"Unsupported geometry type for {region_code}: {geometry_type}"
            )
        if any(
            _polygon_contains(lon, lat, polygon)
            for polygon in polygons
        ):
            matches.add(region_code)

    return [
        region["code"]
        for region in MOROCCO_REGIONS
        if region["code"] in matches
    ]
