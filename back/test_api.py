"""Smoke tests for the NEX TERRA backend.

Run with: .venv/bin/python -m pytest test_api.py -q
"""

import json
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app import routes
from app import geocoding
from app.nasa import client as nasa_client
from app.main import create_app
from app.simulator import engine


TEST_FARM_FIELD = {
    "region_code": "rabat-sale-kenitra",
    "lat": 34.02,
    "lon": -6.84,
    "area_ha": 4.5,
    "irrigation": "rainfed",
}


def _seed_data(data_dir: Path):
    data_dir.mkdir(exist_ok=True)
    (data_dir / "soilgrids.json").write_text(
        json.dumps({"field_code": "SET-001", "soil_type": "loam"}),
        encoding="utf-8",
    )
    (data_dir / "config.json").write_text(
        json.dumps({"scenarios": [
            {"id": "historical", "label": "Historical baseline",
             "temp_shift": 0.0, "precipitation": 1.0, "drought": 0.0},
            {"id": "mild_warming_wet", "label": "Mild warming + wetter",
             "temp_shift": 1.0, "precipitation": 1.05, "drought": 0.0},
            {"id": "severe_drying", "label": "Severe drying",
             "temp_shift": 1.8, "precipitation": 0.78, "drought": 0.35},
            {"id": "hot_wet", "label": "Hot + wet",
             "temp_shift": 2.2, "precipitation": 1.12, "drought": 0.10},
        ]}), encoding="utf-8")
    (data_dir / "crops.json").write_text(
        json.dumps([
            {"code": "winter_wheat", "name": "Winter wheat", "family": "cereal",
             "water_hunger": 0.62, "stress_sensitivity": 0.35,
             "base_et_mm": 420.0, "soil_pref": 0.2, "econ_rev_mad": 18500.0,
             "econ_gwp_m3kg": 1350.0},
            {"code": "barley", "name": "Barley", "family": "cereal",
             "water_hunger": 0.55, "stress_sensitivity": 0.30,
             "base_et_mm": 390.0, "soil_pref": 0.3, "econ_rev_mad": 16500.0,
             "econ_gwp_m3kg": 1250.0},
            {"code": "faba_beans", "name": "Faba beans", "family": "legume",
             "water_hunger": 0.60, "stress_sensitivity": 0.30,
             "base_et_mm": 460.0, "soil_pref": -0.4, "econ_rev_mad": 21000.0,
             "econ_gwp_m3kg": 1100.0},
            {"code": "chickpeas", "name": "Chickpeas", "family": "legume",
             "water_hunger": 0.58, "stress_sensitivity": 0.33,
             "base_et_mm": 440.0, "soil_pref": -0.5, "econ_rev_mad": 25000.0,
             "econ_gwp_m3kg": 1150.0},
            {"code": "lentils", "name": "Lentils", "family": "legume",
             "water_hunger": 0.57, "stress_sensitivity": 0.34,
             "base_et_mm": 430.0, "soil_pref": -0.5, "econ_rev_mad": 26000.0,
             "econ_gwp_m3kg": 1200.0},
            {"code": "sunflower", "name": "Sunflower", "family": "oilseed",
             "water_hunger": 0.52, "stress_sensitivity": 0.28,
             "base_et_mm": 520.0, "soil_pref": 0.1, "econ_rev_mad": 20000.0,
             "econ_gwp_m3kg": 1400.0},
            {"code": "sugar_beet", "name": "Sugar beet", "family": "root",
             "water_hunger": 0.50, "stress_sensitivity": 0.30,
             "base_et_mm": 500.0, "soil_pref": -0.1, "econ_rev_mad": 23000.0,
             "econ_gwp_m3kg": 1300.0},
            {"code": "sweet_potato", "name": "Sweet potato", "family": "tuber",
             "water_hunger": 0.55, "stress_sensitivity": 0.35,
             "base_et_mm": 560.0, "soil_pref": 0.2, "econ_rev_mad": 15000.0,
             "econ_gwp_m3kg": 1500.0},
            {"code": "potato", "name": "Potato", "family": "tuber",
             "water_hunger": 0.50, "stress_sensitivity": 0.30,
             "base_et_mm": 480.0, "soil_pref": -0.2, "econ_rev_mad": 19000.0,
             "econ_gwp_m3kg": 1400.0},
            {"code": "tomato", "name": "Tomato", "family": "vegetable",
             "water_hunger": 0.48, "stress_sensitivity": 0.28,
             "base_et_mm": 520.0, "soil_pref": -0.1, "econ_rev_mad": 32000.0,
             "econ_gwp_m3kg": 1300.0},
            {"code": "onion", "name": "Onion", "family": "vegetable",
             "water_hunger": 0.45, "stress_sensitivity": 0.30,
             "base_et_mm": 400.0, "soil_pref": 0.3, "econ_rev_mad": 26000.0,
             "econ_gwp_m3kg": 1250.0},
            {"code": "carrot", "name": "Carrot", "family": "root",
             "water_hunger": 0.45, "stress_sensitivity": 0.30,
             "base_et_mm": 400.0, "soil_pref": 0.2, "econ_rev_mad": 22000.0,
             "econ_gwp_m3kg": 1250.0},
            {"code": "alfalfa", "name": "Alfalfa", "family": "cover",
             "water_hunger": 0.40, "stress_sensitivity": 0.50,
             "base_et_mm": 650.0, "soil_pref": -0.6, "econ_rev_mad": 12000.0,
             "econ_gwp_m3kg": 900.0},
            {"code": "clover", "name": "Clover", "family": "cover",
             "water_hunger": 0.40, "stress_sensitivity": 0.50,
             "base_et_mm": 600.0, "soil_pref": -0.6, "econ_rev_mad": 9000.0,
             "econ_gwp_m3kg": 850.0},
            {"code": "lettuce", "name": "Lettuce", "family": "vegetable",
             "water_hunger": 0.42, "stress_sensitivity": 0.25,
             "base_et_mm": 300.0, "soil_pref": 0.2, "econ_rev_mad": 24000.0,
             "econ_gwp_m3kg": 1500.0},
            {"code": "maize", "name": "Maize", "family": "cereal",
             "water_hunger": 0.58, "stress_sensitivity": 0.33,
             "base_et_mm": 560.0, "soil_pref": 0.1, "econ_rev_mad": 17000.0,
             "econ_gwp_m3kg": 1500.0},
            {"code": "sorghum", "name": "Sorghum", "family": "cereal",
             "water_hunger": 0.50, "stress_sensitivity": 0.30,
             "base_et_mm": 500.0, "soil_pref": 0.2, "econ_rev_mad": 13000.0,
             "econ_gwp_m3kg": 1300.0},
            {"code": "pulses", "name": "General pulses", "family": "legume",
             "water_hunger": 0.55, "stress_sensitivity": 0.30,
             "base_et_mm": 460.0, "soil_pref": -0.5, "econ_rev_mad": 21000.0,
             "econ_gwp_m3kg": 1150.0},
            {"code": "cereal_mix", "name": "Cereal mix", "family": "cereal",
             "water_hunger": 0.58, "stress_sensitivity": 0.32,
             "base_et_mm": 420.0, "soil_pref": 0.1, "econ_rev_mad": 17500.0,
             "econ_gwp_m3kg": 1300.0},
            {"code": "fallow", "name": "Fallow", "family": "fallow",
             "water_hunger": 0.0, "stress_sensitivity": 0.0,
             "base_et_mm": 0.0, "soil_pref": 0.0, "econ_rev_mad": 0.0,
             "econ_gwp_m3kg": 0.0},
        ]), encoding="utf-8")
    (data_dir / "field.json").write_text(
        json.dumps({
            "field_code": "SET-001", "name": "Demonstration field - Settat",
            "region": "Settat, Rabat-Salé-Kénitra, Morocco", "lat": 32.75,
            "lon": -8.05, "area_ha": 10.0, "terrain": "flat",
            "irrigation": "rainfed",
            "soil": {"soil_type": "loam", "sand_pct": 42.0, "silt_pct": 43.0,
                     "clay_pct": 15.0, "ph": 8.1, "organic_c_pct": 0.9,
                     "nacl_ppth": 6.0},
            "previous_crops": ["winter_wheat", "wheat"],
        }), encoding="utf-8")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(routes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(routes, "FIELD_JSON", tmp_path / "field.json")
    monkeypatch.setattr(routes, "CONFIG_JSON", tmp_path / "config.json")

    def fake_nasa_payload(lat, lon):
        return {
            "temp_mean_c": 16.8,
            "rainfall_mm_tot": 0.0,
            "sun_hours": 5.0,
            "humidity_pct": 45.0,
            "evi": 0.42,
            "sm": 0.30,
            "cmip6": {"temp_mean_c": 18.6, "precipitation_mm": 0.0},
            "_synthetic": True,
            "data_status": "partial",
            "source_status": {
                "temp_mean_c": {"status": "nasa_power", "source": "NASA POWER"},
                "rainfall_mm_tot": {"status": "nasa_power", "source": "NASA POWER"},
            },
            "lat": lat,
            "lon": lon,
            "observed_window_years": [2019, 2024],
            "coverage": {"T2M": 1.0, "PRECTOTCORR": 1.0},
            "source_datasets": ["MERRA2"],
            "source_note": "Test provenance payload.",
        }

    monkeypatch.setattr(routes, "_nasa_payload", fake_nasa_payload)
    _seed_data(tmp_path)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_simulation_preserves_nasa_provenance(client):
    response = client.post(
        "/api/simulate",
        json={
            "crops": ["winter_wheat", "faba_beans", "winter_wheat"],
            "field": TEST_FARM_FIELD,
        },
    )
    assert response.status_code == 200
    nasa = response.json()["nasa"]
    assert nasa["data_status"] == "partial"
    assert nasa["source_status"]["temp_mean_c"]["source"] == "NASA POWER"
    assert nasa["observed_window_years"] == [2019, 2024]
    assert nasa["coverage"]["T2M"] == 1.0


def test_field_endpoint(client):
    r = client.get("/api/field")
    assert r.status_code == 200
    body = r.json()
    assert body["field_code"] == "SET-001"
    assert body["name"].startswith("Demonstration")
    assert body["lat"] == 32.75
    assert body["lon"] == -8.05
    assert body["area_ha"] == 10.0
    assert body["irrigation"] == "rainfed"


def test_soil_endpoint(client):
    r = client.get("/api/soil")
    assert r.status_code == 200
    assert r.json()["soil_type"] == "loam"


def test_history_endpoint(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert len(r.json()) >= 3


def test_scenarios_endpoint(client):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    assert len(r.json()["scenarios"]) == 4


def test_regions_endpoint_lists_all_12_administrative_regions(client):
    response = client.get("/api/regions")
    assert response.status_code == 200
    body = response.json()
    assert len(body["regions"]) == 12
    assert len({region["code"] for region in body["regions"]}) == 12
    assert body["source"]["note"].startswith("The selected region is user-provided")


def test_crop_catalog_exposes_provenance_and_lifecycle(client):
    response = client.get("/api/crops")
    assert response.status_code == 200
    body = response.json()
    crops = {crop["code"]: crop for crop in body["crops"]}
    sources = {source["id"]: source for source in body["sources"]}

    assert len(crops) >= 30
    assert crops["barley"]["national_status"] == "documented"
    assert crops["barley"]["source_ids"][0] in sources
    assert crops["olive"]["life_cycle"] == "perennial"
    assert crops["olive"]["rotation_eligible"] is False
    assert crops["date_palm"]["rotation_eligible"] is False
    assert crops["date_palm"]["documented_regions"] == [
        "draa-tafilalet", "souss-massa", "oriental", "guelmim-oued-noun"
    ]
    assert crops["lentils"]["national_status"] == "documented"
    assert crops["lentils"]["source_ids"] == [
        "ministry-region-rabat-sale-kenitra"
    ]
    assert crops["lentils"]["documented_regions"] == ["rabat-sale-kenitra"]
    for code in (
        "faba_beans", "chickpeas", "sweet_potato", "potato", "tomato",
        "onion", "carrot", "lettuce", "maize", "sorghum",
    ):
        assert crops[code]["national_status"] == "unverified"
        assert crops[code]["source_ids"] == []
        assert crops[code]["documented_regions"] == []
    assert all(
        not crop["rotation_eligible"] or crop["life_cycle"] == "annual"
        for crop in crops.values()
    )
    assert {
        code for code, crop in crops.items() if crop["rotation_eligible"]
    }.issubset(engine.CropDatabase().by_code)


@pytest.mark.parametrize("crop_code", ["alfalfa", "rice"])
def test_non_selectable_crop_is_rejected_from_annual_rotation(client, crop_code):
    response = client.post("/api/simulate", json={
        "crops": [crop_code],
        "field": TEST_FARM_FIELD,
    })
    assert response.status_code == 422
    assert any("annual rotation" in item["msg"] for item in response.json()["detail"])


def test_nasa_endpoint_uses_selected_coordinates(client, monkeypatch):
    seen = {}

    def fake_nasa_payload(lat, lon):
        seen.update(lat=lat, lon=lon)
        return {"lat": lat, "lon": lon}

    monkeypatch.setattr(routes, "_nasa_payload", fake_nasa_payload)
    response = client.get("/api/nasa", params={"lat": 30.25, "lon": -9.2})
    assert response.status_code == 200
    assert seen == {"lat": 30.25, "lon": -9.2}
    assert response.json() == seen


def test_nasa_endpoint_rejects_coordinates_outside_morocco_envelope(client):
    response = client.get("/api/nasa", params={"lat": 40, "lon": -6})
    assert response.status_code == 422


def test_regions_endpoint_includes_boundary_provenance(client):
    response = client.get("/api/regions")
    assert response.status_code == 200
    body = response.json()
    assert len(body["regions"]) == 12
    assert body["boundary_source"]["year"] == 2017
    assert body["boundary_source"]["license"] == (
        "Open Data Commons Open Database License 1.0"
    )


def test_region_boundaries_endpoint_returns_named_geojson_features(client):
    response = client.get("/api/regions/boundaries")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 12
    assert all(
        feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}
        and feature["properties"]["region_code"]
        and feature["properties"]["region_name"]
        for feature in body["features"]
    )


def test_region_location_endpoint_finds_rabat_sale_kenitra(client):
    response = client.get(
        "/api/regions/locate",
        params={"lat": TEST_FARM_FIELD["lat"], "lon": TEST_FARM_FIELD["lon"]},
    )
    assert response.status_code == 200
    assert response.json()["region_codes"] == ["rabat-sale-kenitra"]


def test_region_location_endpoint_rejects_points_outside_mapped_regions(client):
    response = client.get(
        "/api/regions/locate",
        params={"lat": 0.0, "lon": 0.0},
    )
    assert response.status_code == 422
    assert "mapped Moroccan administrative region" in response.json()["detail"]


def test_reverse_place_endpoint_returns_locality_and_context(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "reverse_geocode",
        lambda lat, lon: {
            "place_name": "Agdal",
            "context": "Rabat",
            "attribution_url": "https://www.openstreetmap.org/copyright",
        },
    )

    response = client.get(
        "/api/places/reverse",
        params={"lat": 34.02, "lon": -6.84},
    )

    assert response.status_code == 200
    assert response.json()["place_name"] == "Agdal"
    assert response.json()["context"] == "Rabat"
    assert response.json()["attribution_url"].endswith("/copyright")


def test_reverse_place_endpoint_returns_empty_locality_when_unavailable_in_map_data(
    client, monkeypatch
):
    monkeypatch.setattr(routes, "reverse_geocode", lambda lat, lon: None)

    response = client.get(
        "/api/places/reverse",
        params={"lat": 34.02, "lon": -6.84},
    )

    assert response.status_code == 200
    assert response.json()["place_name"] is None


def test_reverse_place_endpoint_reports_lookup_service_failure(client, monkeypatch):
    def fail_lookup(lat, lon):
        raise RuntimeError("Nearby locality lookup is temporarily unavailable.")

    monkeypatch.setattr(routes, "reverse_geocode", fail_lookup)

    response = client.get(
        "/api/places/reverse",
        params={"lat": 34.02, "lon": -6.84},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Nearby locality lookup is temporarily unavailable."
    )


def test_reverse_geocoder_returns_precise_locality_and_caches_result(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "address": {
                    "neighbourhood": "Agdal",
                    "city": "Rabat",
                    "country": "Morocco",
                }
            }

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(geocoding.requests, "get", fake_get)
    monkeypatch.setattr(geocoding.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(geocoding, "_cache", OrderedDict())
    monkeypatch.setattr(geocoding, "_last_request_at", 0.0)

    first = geocoding.reverse_geocode(34.02, -6.84)
    second = geocoding.reverse_geocode(34.02001, -6.84001)

    assert first == second
    assert first["place_name"] == "Agdal"
    assert first["context"] == "Rabat"
    assert len(calls) == 1
    assert calls[0][1]["params"]["format"] == "jsonv2"
    assert calls[0][1]["headers"]["User-Agent"]
    assert calls[0][1]["headers"]["Accept-Language"] == "fr,en"


def test_simulate_endpoint(client):
    payload = {
        "crops": ["winter_wheat", "faba_beans", "winter_wheat"],
        "field": TEST_FARM_FIELD,
    }
    r = client.post("/api/simulate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["rotation"] == ["winter_wheat", "faba_beans", "winter_wheat"]
    assert body["water_total_mm"] > 0
    assert "resilience_avg" in body
    assert body["score"] > 0
    assert body["priority_weights"]["water"] == 0.2
    assert body["nasa"]["_synthetic"] is True


def test_compare_endpoint(client):
    payload = {
        "crops": ["winter_wheat", "winter_wheat", "winter_wheat"],
        "field": TEST_FARM_FIELD,
    }
    r = client.post("/api/compare", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert len(body["comparison"]) == 12
    assert len(body["ranked"]) == 3
    assert len(body["scenario_winners"]) == 4
    historical = [row for row in body["comparison"]
                  if row["scenario_id"] == "historical"]
    assert len({tuple(row["rotation"]) for row in historical}) == 3
    assert all(
        sum(row["scenario_id"] == scenario_id for row in body["comparison"]) == 3
        for scenario_id in body["scenario_ids"]
    )
    names = body["rotation_names"]
    assert "current" in names
    assert "cereal_legume" in names
    assert "diversified" in names
    assert body["field"]["lat"] == TEST_FARM_FIELD["lat"]
    assert body["nasa"]["lat"] == TEST_FARM_FIELD["lat"]
    context = body["comparison_context"]
    assert context["score_status"] == "illustrative prototype heuristic"
    assert context["field_soil_status"] == "prototype defaults; not measured"
    assert "do not calibrate" in context["nasa_role"]
    assert any("synthetic" in item.lower() for item in context["score_inputs"])
    cereal_legume = next(
        strategy for strategy in body["strategies"]
        if strategy["id"] == "cereal_legume"
    )
    faba_evidence = next(
        crop for crop in cereal_legume["crop_evidence"]
        if crop["code"] == "faba_beans"
    )
    assert faba_evidence["national_status"] == "unverified"
    assert any("data gap, not evidence of absence" in item
               for item in cereal_legume["data_gaps"])


def test_recommendations_generate_three_options_without_current_rotation(client):
    response = client.post("/api/recommendations", json={
        "field": TEST_FARM_FIELD,
        "scenario_id": "historical",
    })
    assert response.status_code == 200
    body = response.json()
    assert len(body["strategies"]) == 3
    assert [item["id"] for item in body["strategies"]] == [
        "suggested_1", "suggested_2", "suggested_3",
    ]
    rotations = [item["rotation"] for item in body["strategies"]]
    assert all(len(rotation) == 3 and len(set(rotation)) == 3
               for rotation in rotations)
    assert len({tuple(rotation) for rotation in rotations}) == 3
    simulator = engine.Rotator()
    assert all(
        len({simulator.crops.crop(code).family for code in rotation}) == 3
        for rotation in rotations
    )
    assert len(body["comparison"]) == 12
    assert len(body["ranked"]) == 3
    assert body["comparison_context"]["score_status"] == (
        "illustrative prototype heuristic"
    )
    assert all(item["crop_evidence"] for item in body["strategies"])


def test_recommendations_can_include_an_optional_current_rotation(client):
    current_rotation = ["winter_wheat", "barley", "lentils"]
    response = client.post("/api/recommendations", json={
        "field": TEST_FARM_FIELD,
        "scenario_id": "historical",
        "current_rotation": current_rotation,
    })
    assert response.status_code == 200
    body = response.json()
    current = next(item for item in body["strategies"] if item["id"] == "current")
    assert current["rotation"] == current_rotation
    assert len(body["strategies"]) == 4
    assert len(body["comparison"]) == 16


def test_recommendations_remain_available_with_synthetic_climate_data(
    client, monkeypatch
):
    monkeypatch.setattr(routes, "_nasa_payload", lambda lat, lon: {
        "data_status": "synthetic",
        "_synthetic": True,
        "evi": 0.42,
        "sm": 0.30,
        "source_note": "NASA POWER unavailable; synthetic fallback.",
    })
    response = client.post("/api/recommendations", json={
        "field": TEST_FARM_FIELD,
        "scenario_id": "historical",
    })
    assert response.status_code == 200
    body = response.json()
    assert len(body["strategies"]) == 3
    assert body["comparison_context"]["nasa_data_status"] == "synthetic"
    assert "do not calibrate" in body["comparison_context"]["nasa_role"]


def test_recommendations_reject_non_selectable_current_crop(client):
    response = client.post("/api/recommendations", json={
        "field": TEST_FARM_FIELD,
        "current_rotation": ["alfalfa", "barley", "lentils"],
    })
    assert response.status_code == 422
    assert any("annual rotation" in item["msg"]
               for item in response.json()["detail"])


def test_optimize_endpoint(client):
    payload = {
        "crops": ["winter_wheat", "faba_beans", "winter_wheat"],
        "field": TEST_FARM_FIELD,
    }
    r = client.post("/api/optimize", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "optimized_rotation" in body
    assert len(body["optimized_rotation"]) >= 1
    assert body["score"] > 0


def test_demo_seed_endpoint(client):
    r = client.get("/api/demo/seed.json")
    assert r.status_code == 200
    body = r.json()
    assert "scenarios" in body
    assert "rotation_names" in body
    assert "fields" not in body
    assert "nasa" not in body
    assert len(body["current_rotation"]) == 3


def test_priorities_affect_simulation(client):
    crops = ["winter_wheat", "faba_beans", "winter_wheat"]
    water_result = client.post("/api/simulate", json={
        "crops": crops,
        "field": TEST_FARM_FIELD,
        "priorities": {
            "water": 1, "nitrogen": 0, "resilience": 0, "soil": 0, "economy": 0,
        },
    })
    economy_result = client.post("/api/simulate", json={
        "crops": crops,
        "field": TEST_FARM_FIELD,
        "priorities": {
            "water": 0, "nitrogen": 0, "resilience": 0, "soil": 0, "economy": 1,
        },
    })
    assert water_result.status_code == 200
    assert economy_result.status_code == 200
    assert water_result.json()["score"] != economy_result.json()["score"]
    assert water_result.json()["priority_weights"]["water"] == 1.0
    assert economy_result.json()["priority_weights"]["economy"] == 1.0
    invalid_result = client.post("/api/simulate", json={
        "crops": crops,
        "field": TEST_FARM_FIELD,
        "priorities": {
            "water": 0, "nitrogen": 0, "resilience": 0, "soil": 0, "economy": 0,
        },
    })
    assert invalid_result.status_code == 422


def test_unknown_crop_is_reported_as_client_error(client):
    response = client.post("/api/simulate", json={
        "crops": ["not_a_crop"],
        "field": TEST_FARM_FIELD,
    })
    assert response.status_code == 422
    assert any(
        "Unknown or non-selectable crop code" in item["msg"]
        for item in response.json()["detail"]
    )


def test_comparison_requires_a_selected_field(client):
    response = client.post(
        "/api/compare",
        json={"crops": ["winter_wheat", "barley"]},
    )
    assert response.status_code == 422
    assert "Select a Moroccan field location" in response.json()["detail"]


def test_comparison_rejects_region_that_does_not_match_coordinates(client):
    field = {**TEST_FARM_FIELD, "region_code": "casablanca-settat"}
    response = client.post(
        "/api/compare",
        json={"crops": ["winter_wheat", "barley"], "field": field},
    )
    assert response.status_code == 422
    assert any(
        "Coordinates fall within Rabat-Sale-Kenitra" in item["msg"]
        for item in response.json()["detail"]
    )


@pytest.mark.parametrize(
    "field_changes",
    [
        {"region_code": "not-a-region"},
        {"lat": 40.0},
        {"area_ha": 0.0},
        {"soil": {"sand_pct": 40.0}},
        {"soil": {"sand_pct": 30.0, "silt_pct": 30.0, "clay_pct": 30.0}},
    ],
)
def test_comparison_rejects_invalid_field_inputs(client, field_changes):
    field = {**TEST_FARM_FIELD, **field_changes}
    response = client.post(
        "/api/compare",
        json={"crops": ["winter_wheat", "barley"], "field": field},
    )
    assert response.status_code == 422


def test_optimizer_maximizes_weighted_score(monkeypatch):
    rotator = engine.Rotator()
    soil = engine.build_soil_profile({})
    climate = engine.default_climate()
    priorities = {
        "water": 0.1, "nitrogen": 0.1, "resilience": 0.1,
        "soil": 0.1, "economy": 0.6,
    }
    candidates = ["winter_wheat", "barley", "faba_beans"]
    candidate_scores = [
        rotator.score_rotation(
            [crop], soil, climate, priority_weights=priorities
        )["score"]
        for crop in candidates
    ]

    def fake_differential_evolution(objective, bounds, **kwargs):
        points = [[float(index)] for index in range(len(candidates))]
        values = [objective(point) for point in points]
        best_index = min(range(len(values)), key=values.__getitem__)
        return SimpleNamespace(
            x=points[best_index], fun=values[best_index],
            nit=1, success=True,
        )

    monkeypatch.setattr(engine, "differential_evolution", fake_differential_evolution)
    result = rotator.optimize(
        soil, climate, priorities, max_seasons=1,
    )
    expected_index = max(
        range(len(candidate_scores)), key=candidate_scores.__getitem__
    )
    assert result["optimized_rotation"] == [candidates[expected_index]]
    assert result["score"] == candidate_scores[expected_index]


def test_power_daily_request_and_aggregation(monkeypatch):
    start = date(2024, 1, 1)
    end = date(2024, 12, 31)
    temperatures = {}
    rainfall = {}
    temp_minimum = {}
    temp_maximum = {}
    humidity = {}
    wind = {}
    solar_radiation = {}
    pressure = {}
    day = start
    while day <= end:
        key = day.strftime("%Y%m%d")
        temperatures[key] = 15.0
        rainfall[key] = 0.1
        temp_minimum[key] = 8.0
        temp_maximum[key] = 22.0
        humidity[key] = 60.0
        wind[key] = 2.0
        solar_radiation[key] = 15.0
        pressure[key] = 99.0
        day += timedelta(days=1)
    payload = {
        "properties": {
            "parameter": {
                "T2M": temperatures,
                "PRECTOTCORR": rainfall,
                "T2M_MIN": temp_minimum,
                "T2M_MAX": temp_maximum,
                "RH2M": humidity,
                "WS2M": wind,
                "ALLSKY_SFC_SW_DWN": solar_radiation,
                "PS": pressure,
            },
        },
        "geometry": {"type": "Point", "coordinates": [-8.05, 32.75, 179.0]},
        "header": {
            "fill_value": -999.0,
            "sources": ["MERRA2"],
            "api": {"version": "v2.10.3"},
            "time_standard": "UTC",
        },
    }
    request_data = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    def fake_get(url, params, headers, timeout):
        request_data.update(
            url=url, params=params, headers=headers, timeout=timeout
        )
        return FakeResponse()

    monkeypatch.setattr(nasa_client.requests, "get", fake_get)
    result = nasa_client._fetch_power_daily(32.75, -8.05, 2024, 2024)

    assert request_data["url"] == nasa_client.POWER_DAILY_URL
    assert request_data["params"] == {
        "parameters": (
            "T2M,PRECTOTCORR,T2M_MIN,T2M_MAX,RH2M,WS2M,"
            "ALLSKY_SFC_SW_DWN,PS"
        ),
        "community": "AG",
        "longitude": "-8.05000",
        "latitude": "32.75000",
        "start": "20240101",
        "end": "20241231",
        "format": "JSON",
        "time-standard": "UTC",
    }
    assert request_data["timeout"] == (5, 25)
    assert result["temp_mean_c"] == 15.0
    assert result["rainfall_mm_tot"] == 36.6
    assert result["coverage"]["T2M"] == 1.0
    assert result["coverage"]["PRECTOTCORR"] == 1.0
    assert result["coverage"]["ET0"] == 1.0
    assert result["series"]["2024-01"]["rainfall_mm"] == 3.1
    assert result["series"]["2024-01"]["et0_mm"] > 0
    assert result["et0_mean_mm_day"] > 0
    assert result["humidity_mean_pct"] == 60.0
    assert result["solar_radiation_mean_mj_m2_day"] == 15.0
    assert result["elevation_m"] == 179.0
    assert result["source_datasets"] == ["MERRA2"]


def test_power_parser_rejects_malformed_or_low_coverage_data():
    with pytest.raises(ValueError, match="JSON object"):
        nasa_client._parse_power_daily_payload(
            None, date(2024, 1, 1), date(2024, 1, 1), 32.75
        )

    sparse = {
        "properties": {
            "parameter": {
                "T2M": {"20240101": -999},
                "PRECTOTCORR": {"20240101": 0.0},
            },
        },
        "header": {"fill_value": -999},
    }
    with pytest.raises(ValueError, match="coverage"):
        nasa_client._parse_power_daily_payload(
            sparse, date(2024, 1, 1), date(2024, 1, 1), 32.75
        )

    core_only = {
        "properties": {
            "parameter": {
                "T2M": {"20240101": 15.0},
                "PRECTOTCORR": {"20240101": 0.0},
            },
        },
        "header": {"fill_value": -999},
    }
    result = nasa_client._parse_power_daily_payload(
        core_only, date(2024, 1, 1), date(2024, 1, 1), 32.75
    )
    assert result["temp_mean_c"] == 15.0
    assert result["et0_mean_mm_day"] is None
    assert "elevation" in result["et0_reason"]


def test_fao56_et0_matches_reference_example():
    et0 = nasa_client._calculate_fao56_et0(
        day=date(2023, 7, 6),
        t_max_c=21.5,
        t_min_c=12.3,
        actual_vapour_pressure_kpa=1.409,
        wind_speed_ms=2.078,
        solar_radiation_mj_m2_day=22.07,
        surface_pressure_kpa=100.1,
        latitude_deg=50.8,
        elevation_m=100.0,
    )
    assert et0 == pytest.approx(3.9, abs=0.15)


def test_nasa_composite_cache_is_scoped_to_field(tmp_path, monkeypatch):
    monkeypatch.setattr(nasa_client, "NASA_DIR", tmp_path)
    calls = []

    def fake_power(lat, lon, start_year, end_year):
        calls.append((lat, lon, start_year, end_year))
        return {
            "temp_mean_c": 16.8,
            "rainfall_mm_tot": 100.0,
            "series": {},
            "coverage": {
                "T2M": 1.0,
                "PRECTOTCORR": 1.0,
                "T2M_MIN": 1.0,
                "T2M_MAX": 1.0,
                "RH2M": 1.0,
                "WS2M": 1.0,
                "ALLSKY_SFC_SW_DWN": 1.0,
                "PS": 1.0,
                "ET0": 1.0,
            },
            "humidity_mean_pct": 45.0,
            "solar_radiation_mean_mj_m2_day": 15.0,
            "temp_min_mean_c": 10.0,
            "temp_max_mean_c": 20.0,
            "wind_mean_ms": 2.0,
            "surface_pressure_mean_kpa": 99.0,
            "et0_mean_mm_day": 3.0,
            "et0_coverage_fraction": 1.0,
            "et0_input_coverage": {},
            "elevation_m": 179.0,
            "et0_reason": None,
            "source_datasets": ["MERRA2"],
            "api_version": "v2.10.3",
            "time_standard": "UTC",
        }

    monkeypatch.setattr(nasa_client, "_fetch_power_daily", fake_power)
    first = nasa_client.fetch_nasa_series(32.75, -8.05, 2024, 2024)
    cached = nasa_client.fetch_nasa_series(32.75, -8.05, 2024, 2024)
    other_field = nasa_client.fetch_nasa_series(33.0, -7.0, 2024, 2024)

    assert len(calls) == 2
    assert cached["source_status"]["temp_mean_c"]["status"] == "nasa_power"
    assert first["data_status"] == "partial"
    assert first["_synthetic"] is True
    assert first["source_status"]["et0"]["status"] == "derived"
    assert first["et0_mean_mm_day"] == 3.0
    assert other_field["lat"] == 33.0
    assert len(list(tmp_path.glob("composite_nasa_*.json"))) == 2


def test_nasa_power_failure_is_marked_synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(nasa_client, "NASA_DIR", tmp_path)

    def fail_power(*args, **kwargs):
        raise nasa_client.requests.Timeout("offline in test")

    monkeypatch.setattr(nasa_client, "_fetch_power_daily", fail_power)
    payload = nasa_client.fetch_nasa_series(32.75, -8.05, 2024, 2024)

    assert payload["data_status"] == "synthetic"
    assert payload["_synthetic"] is True
    assert payload["source_status"]["temp_mean_c"]["status"] == "synthetic"
    assert payload["source_status"]["et0"]["status"] == "unavailable"
    assert "synthetic placeholders" in payload["source_note"]


@pytest.mark.parametrize(
    ("configured_origins", "origin"),
    [
        (
            "https://nexterra.example, https://www.nexterra.example/",
            "https://www.nexterra.example",
        ),
        (None, "http://localhost:5173"),
    ],
)
def test_cors_allows_configured_and_local_origins(
    monkeypatch, configured_origins, origin
):
    if configured_origins is None:
        monkeypatch.delenv("NEX_TERRA_ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("NEX_TERRA_ALLOWED_ORIGINS", configured_origins)

    with TestClient(create_app()) as test_client:
        response = test_client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
