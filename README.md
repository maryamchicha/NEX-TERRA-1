# NEX TERRA — Rotation Resilience Engine

Agricultural decision-support prototype for Moroccan farmers. It compares
rotation strategies under illustrative climate scenarios and exposes the
model's assumptions and data limitations. The interface is organized as a
guided sequence of separate pages: **Home**, **About**, **Agricultural Data**,
**Simulation**, **Results**, **Methodology**, and **Team**.

Built with:

* **Backend**: FastAPI + Uvicorn, Python (`back/`)
* **Frontend**: Vite + React + Leaflet (`front/`)
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
administrative regions and choose the exact farm point by clicking the map.
Click a region to select it and zoom in; click again to refine the marker.
Coordinates are displayed beneath the map, and the region is detected from the
administrative boundaries. Confirm the location and enter the remaining farm
details before continuing. Coordinates and region can also be entered manually;
points on a shared boundary may require choosing between matching regions.
NASA POWER is queried for the selected point.

The top navigation and Previous/Next controls switch between separate
hash-routed views. Field and simulation state is retained while moving between
pages; the browser back and forward controls also follow the page sequence.

### Optional accounts and saved farm profiles

The account panel uses Supabase Auth and PostgreSQL. To enable it:

1. Create a Supabase project and choose a region appropriate for your users and
   data-residency needs. The current Supabase Free plan includes 500 MB of
   database storage and may pause projects after a week without activity.
2. Run both SQL files in `supabase/migrations/` in filename order. They create
   the one-profile-per-account table and opt-in simulation history, with row
   level security policies that restrict each record to its authenticated
   owner.
3. Copy `front/.env.example` to `front/.env.local` and set
   `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` from the Supabase
   project. The publishable key is intended for browser use; **never put a
   secret/service-role key in
   frontend variables or commit real credentials**.
4. Restart Vite, create an account, and confirm the email if email confirmation
   is enabled in the Supabase Auth settings. A signed-in user must explicitly
   consent before saving field coordinates and farmer-reported details. Saving
   a simulation requires separate consent on the Results page.

Without these environment variables, the app continues to work without
accounts. Each account stores one selected field and baseline; saving again
updates that saved profile. Simulation runs are saved only after separate,
explicit consent on the Results page and can be reloaded or deleted from the
account's history. The simulator remains available to visitors without an
account. The Supabase project and production email configuration are not
provisioned by this repository.

## Free public deployment with Vercel and Supabase

The repository is configured for one Vercel project: Vercel builds the React
frontend from `front/` and runs the FastAPI application as a Python Function.
The frontend and API share one HTTPS origin, so `VITE_API_BASE_URL` can remain
unset. Vercel's [Hobby plan](https://vercel.com/docs/plans/hobby) is listed as
free and intended for personal projects; Vercel documents
[FastAPI/Python support](https://vercel.com/docs/frameworks/backend/fastapi).
The plan has usage limits. Do not select a paid plan or enter payment details
if your account asks for them.

1. In Vercel, import the public GitHub repository
   [`manabouate-cell/NEX-TERRA`](https://github.com/manabouate-cell/NEX-TERRA).
   Keep the project root at the repository root; the build settings in
   `pyproject.toml` install the frontend dependencies and build `front/`.
2. After the first deployment, copy its public HTTPS URL. In Vercel's project
   settings, add `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` as
   environment variables if accounts and saved farm profiles are wanted.
   Redeploy after setting or changing these values. The publishable key is
   intended for browser use with the migration's RLS policies; never add a
   service-role key to frontend variables.
3. In Supabase Auth, set the Site URL and allowed redirect URLs to the actual
   Vercel URL. Create a Supabase project on its Free plan and run both SQL
   migrations in filename order. Authentication is optional for the public
   simulation; it is required only to save a farm profile or simulation run.
4. Verify the homepage, `/health`, the `/api/` routes, field selection,
   simulation, page refresh/navigation, and (if enabled) consented profile and
   simulation save/load/delete before sharing the URL.

Vercel Hobby includes monthly usage limits; deployments or functions may be
limited after those free allowances are reached. Supabase Free projects may
pause after a week without activity, have no downloadable database backups,
and include limited storage. These free tiers are suitable for a demonstration,
not guaranteed 24/7 production service. If Vercel asks for a payment method or
paid upgrade, stop rather than entering card details.

Never put a Supabase secret/service-role key in the frontend or commit real
credentials. The app is an exploratory prototype: its rotation scores and
crop-water assumptions are not validated agronomic advice.

## Licensing and acknowledgements

Original NEX TERRA source code is licensed under Apache License 2.0; see
[`LICENSE`](LICENSE). Third-party data, software dependencies, and visual
assets retain their own licenses and terms. The source and data references
used by the application are listed in the website footer and described in
this README.

The hero artwork was supplied to the project by its owner and is not covered
by the source-code license. Confirm the right to publish and redistribute it
before making the application public. The app uses NASA POWER data and names
NASA only to identify that source; it does not use a NASA logo or claim NASA
endorsement, certification, or partnership.

Direct frontend dependencies: [React](https://github.com/facebook/react/blob/main/LICENSE),
[React Router](https://github.com/remix-run/react-router/blob/main/LICENSE.md),
[Supabase JavaScript](https://github.com/supabase/supabase-js/blob/master/LICENSE),
[Vite](https://github.com/vitejs/vite/blob/main/LICENSE), and
[@vitejs/plugin-react](https://github.com/vitejs/vite/blob/main/LICENSE) use
the MIT License; [Leaflet](https://github.com/Leaflet/Leaflet/blob/main/LICENSE)
uses the BSD 2-Clause License. Morocco administrative boundaries use the
geoBoundaries GB Open ADM1 dataset under ODbL 1.0; basemap tiles and place-name
lookups are credited to OpenStreetMap contributors. Source links and notices
are shown in the website footer and repository.

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

The region selector lists Morocco's 12 administrative regions. The map uses
the generalized boundaries described above to detect the selected region;
points outside mapped regions are not accepted as a field location. Soil
measurements may be entered by the farmer. If none are supplied, the prototype
uses default soil assumptions and labels them as unmeasured.

After a field is selected, the app generates three exploratory annual-crop
sequences from the simulator's supported crop pool, using the selected
illustrative climate scenario, soil inputs, and farmer priorities. The farmer's
current rotation is optional and can be added as a baseline. Each option shows
crop evidence, region-level data gaps, and risks. Generated sequence positions
are not regional planting calendars; crop coefficients and scores remain
unvalidated prototype assumptions. NASA POWER observations are displayed as
local climate context and do not directly calibrate the crop coefficients or
rotation score.

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
| `/api/recommendations` | POST `{"field":{...},"scenario_id":"historical","priorities":{...},"current_rotation":null}` | Generate three exploratory rotations, optionally comparing the farmer's current rotation |
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
