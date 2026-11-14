# NEX TERRA — Rotation Resilience Engine

Agricultural decision-support prototype for Moroccan farmers. It compares
rotation strategies under illustrative climate scenarios and exposes the
model's assumptions and data limitations. A three-step demo: **pick a field**,
**simulate a rotation**, **compare / optimize**.

Built with:

* **Backend**: FastAPI + Uvicorn, Python 3.13 (`nex_terra/back/`)
* **Frontend**: Vite + React + Leaflet (`nex_terra/front/`)
* **Data**: farmer-selected field coordinates and optional soil measurements;
  NASA POWER daily climate estimates are retrieved for the selected point.
  Crop coefficients and rotation scores remain prototype assumptions.

---

## Run it

### 1. Start the backend

```bash
cd nex_terra/back
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The first boot takes a few seconds. Health:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"nex-terra","engine":"rotation-simulator"}
```

> The port 8000 must be free. If you see `ERROR: [Errno 98] address
> already in use`, kill the process holding it (see
> [port-in-use troubleshooting](#port-8000-address-already-in-use)) and
> retry.

### 2. Start the frontend

```bash
cd nex_terra/front
npm run dev
```

Then open **http://localhost:5173** in a browser. Select one of Morocco's 12
administrative regions and choose the field point by clicking the map or
entering coordinates. Click a region outline on the map to set both the field
point and region; clicking elsewhere sets only the point. The selected region
is checked against the mapped administrative boundaries before the field is
accepted. NASA POWER is queried for the selected point.

### Administrative-region boundaries

The region list uses Morocco's 12 administrative regions. Coordinate checks use
the simplified geoBoundaries GB Open Morocco ADM1 dataset, represented as 2017
boundaries and sourced from OpenStreetMap/Wambacher. The dataset is included at
`back/data/morocco_admin1_simplified.geojson` and licensed under the
[Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Source data and release reference:
[geoBoundaries Morocco ADM1](https://github.com/wmgeolab/geoBoundaries/tree/9469f09/releaseData/gbOpen/MAR/ADM1).

Both the frontend and API reject a field when its selected region does not match
its coordinates. Points on shared boundaries may match both neighboring
regions. These generalized boundaries support location checks only; they are
not legal boundaries or a substitute for precise surveying.

> To use the minified production build instead, the backend serves
> `nex_terra/front/dist/` at `/` when it exists.

---

## NASA data

`GET /api/nasa?lat={latitude}&lon={longitude}` and the `nasa` object in
simulation/comparison responses use NASA POWER's
[Daily Point API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/).
For the selected field point and 2019–2024 window, `T2M` is averaged and
`PRECTOTCORR` is summed after fill values are excluded. NASA POWER also
provides `T2M_MIN`, `T2M_MAX`, `RH2M`, `WS2M`, `ALLSKY_SFC_SW_DWN`, and `PS`
for a daily reference evapotranspiration estimate. The response includes
parameter-level provenance and coverage; core weather parameters require at
least 95% daily coverage.

POWER values are **gridded climate estimates**, not field-sensor measurements.
Daily FAO-56 Penman–Monteith reference ET0 is computed only when NASA POWER
inputs have at least 95% complete-day coverage and supplies site elevation.
Actual vapour pressure uses the FAO mean-relative-humidity approximation.
ET0 represents a standard grass reference surface, not a crop-specific water
need or irrigation recommendation. NASA POWER observed weather and reference
ET0 provide climate context; they do not calibrate crop coefficients or
directly determine the prototype rotation score. Synthetic EVI and
soil-moisture placeholders are fed into its
resilience component. Sunshine duration and future-climate values also remain
synthetic placeholders. `data_status` is `partial` when core POWER values are
available and `synthetic` when their
request fails or misses the coverage threshold. The frontend displays data
sources and coverage, plus a year-selectable monthly chart; synthetic series
are not plotted as NASA data.

The ET0 method follows [FAO-56 Chapter 4](https://www.fao.org/4/x0490e/x0490e08.htm)
and [Chapter 3](https://www.fao.org/4/x0490e/x0490e07.htm).

Composite responses are cached per location and year range for 24 hours under
`back/data/nasa/`. Demo seed values are always synthetic. This remains a
prototype, not validated agronomic advice.

The region selector lists Morocco's 12 administrative regions. Coordinates are
restricted to a broad Morocco envelope; exact regional boundaries are not
loaded, so the selected region is not inferred or validated from the point.
Soil measurements may be entered by the farmer. If none are supplied, the
prototype uses default soil assumptions and labels them as unmeasured.

## Crop catalog and evidence

`GET /api/crops` returns annual and perennial crops, crop groups, source links,
evidence status, and any administrative regions explicitly named by a source.
The catalog is based on the Moroccan Ministry of Agriculture's sector profiles
and cereal-production reports. An empty regional list means the region-level
evidence is unknown; it does not mean the crop is absent there. Irrigation
perimeters and named plains are not converted into administrative regions.

The catalog uses national sector reports and regional Ministry profiles to
distinguish documented crops from simulator options whose presence has not yet
been verified. A regional entry is recorded only when the source explicitly
names the crop and administrative region; for example, the Rabat-Salé-Kénitra
profile names lentille d'Ain Sbit and lentille de Zaer. Unverified entries
remain clearly labelled prototype inputs, not verified crop availability.
Perennial crops and non-species groups appear in the catalog but are rejected
by annual-rotation API requests. Only annual crops with existing prototype
coefficients can be selected for a rotation. Their scores and crop-water values
remain unvalidated; no regional crop calendar or crop-specific water schedule
is inferred from the sources.

The comparison response includes crop-by-crop source evidence and data gaps.
Its weighted score uses prototype crop coefficients, user-selected priorities,
soil measurements when supplied (otherwise defaults), illustrative scenario
deltas, and synthetic vegetation/soil-moisture inputs. A higher score is not
an agronomic recommendation. The modeled water-demand estimate is not an
irrigation schedule, and the economic value is a gross-revenue assumption,
not a net margin.

---

## API overview

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Service health |
| `/api/regions` | GET | Morocco's 12 administrative region choices |
| `/api/crops` | GET | Crop catalog with lifecycle, evidence status, sources, and documented regions |
| `/api/field` | GET | Legacy Settat example field |
| `/api/soil` | GET | Legacy prototype soil profile (not a live SoilGrids query) |
| `/api/history` | GET | Past rotations (demo archive) |
| `/api/scenarios` | GET | Four illustrative climate scenarios (not validated projections) |
| `/api/nasa?lat={latitude}&lon={longitude}` | GET | NASA POWER estimates for the selected point |
| `/api/simulate` | POST `{"crops":[...],"field":{...}}` | Simulate a rotation for the selected field |
| `/api/compare` | POST `{"crops":[...],"field":{...},"priorities":{...}}` | Compare the supplied rotation and two illustrative alternatives across scenarios |
| `/api/optimize` | POST `{"crops":[...],"field":{...},"priorities":{...}}` | Optimize the weighted prototype score for the selected field |
| `/api/demo/seed.json` | GET | Rotation defaults and illustrative climate scenarios (no default farm or NASA data) |

Example `simulate` request:

```json
{
  "crops": ["winter_wheat", "faba_beans", "winter_wheat"],
  "field": {
    "region_code": "rabat-sale-kenitra",
    "lat": 34.02,
    "lon": -6.84,
    "area_ha": 4.5,
    "irrigation": "rainfed"
  },
  "priorities": { "water": 0.2, "nitrogen": 0.15, "resilience": 0.25, "soil": 0.2, "economy": 0.2 },
  "soil": { "soil_type": "loam", "sand_pct": 42, "silt_pct": 43, "clay_pct": 15, "ph": 8.1, "organic_c_pct": 0.9, "nacl_ppth": 6 },
  "climate": { "id": "baseline", "temp_shift": 0, "precipitation": 1, "drought": 0 }
}
```

All numeric fields are deterministic (no randomness).

## Port 8000 — address already in use

If you get:

```
ERROR: [Errno 98] address already in use
```

find and kill the holder:

```bash
# find the PID
ss -tlnp 2>/dev/null | grep :8000
# or
pgrep -af "uvicorn app.main"

# kill it
kill -9 <PID>
```

Then retry. This commonly happens when a previous backend process was
left running from an earlier session.

---
