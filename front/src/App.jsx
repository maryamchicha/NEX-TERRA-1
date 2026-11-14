import { useEffect, useState, useCallback } from 'react'
import L from 'leaflet'

const DEFAULT_CROPS = ['winter_wheat', 'winter_wheat', 'winter_wheat']
const DEFAULT_FIELD_DRAFT = {
  region_code: '',
  lat: '',
  lon: '',
  area_ha: '',
  irrigation: 'unknown',
  soil_type: '',
  sand_pct: '',
  silt_pct: '',
  clay_pct: '',
  ph: '',
  organic_c_pct: '',
  nacl_ppth: '',
}
const PRIORITY_LABELS = {
  water: 'Water saving',
  nitrogen: 'Nitrogen balance',
  resilience: 'Climate resilience',
  soil: 'Soil protection',
  economy: 'Economic potential',
}
const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// ---- helpers ----
async function api(path, opts) {
  const res = await fetch(path, opts)
  if (!res.ok) {
    let msg = `Request failed: ${res.status}`
    try { msg = (await res.json()).detail || msg }
    catch (_) {}
    throw new Error(msg)
  }
  return res.json()
}

function sourceLabel(source) {
  if (!source) return 'provenance unavailable'
  if (source.status === 'derived') {
    const coverage = Number.isFinite(source.coverage_fraction)
      ? `, ${(source.coverage_fraction * 100).toFixed(1)}% complete days`
      : ''
    return `${source.source}${coverage}`
  }
  if (source.status === 'unavailable') return 'unavailable'
  if (source.status !== 'nasa_power') return 'synthetic placeholder'
  const coverage = Number.isFinite(source.coverage_fraction)
    ? `, ${(source.coverage_fraction * 100).toFixed(1)}% coverage`
    : ''
  return `${source.source}${coverage}`
}

// ---- small Sparkline-free rank label ----
function RankBadge({ rank }) {
  const cls = { 1: 'rank-1', 2: 'rank-2', 3: 'rank-3' } [String(rank)] || ''
  return <span className={`rank-badge ${cls}`}>{rank}</span>
}

function PowerMonthlyChart({ nasaData }) {
  const series = nasaData.series && typeof nasaData.series === 'object'
    ? nasaData.series
    : {}
  const years = [...new Set(
    Object.keys(series)
      .filter((key) => /^\d{4}-\d{2}$/.test(key))
      .map((key) => key.slice(0, 4))
  )].sort()
  const [selectedYear, setSelectedYear] = useState('')
  const year = years.includes(selectedYear) ? selectedYear : years[years.length - 1]

  if (!year) {
    return (
      <div className="card">
        <h2>NASA POWER monthly climate</h2>
        <p className="sub">No monthly NASA POWER series is available; synthetic values are not plotted.</p>
      </div>
    )
  }

  const months = MONTH_LABELS.map((label, index) => {
    const key = `${year}-${String(index + 1).padStart(2, '0')}`
    const values = series[key] || {}
    return {
      label,
      temperature: Number.isFinite(values.temp_mean_c) ? values.temp_mean_c : null,
      precipitation: Number.isFinite(values.rainfall_mm) ? values.rainfall_mm : null,
      et0: Number.isFinite(values.et0_mm) ? values.et0_mm : null,
    }
  })
  const temperatures = months
    .map((month) => month.temperature)
    .filter(Number.isFinite)
  const precipitation = months
    .map((month) => month.precipitation)
    .filter(Number.isFinite)
  const et0Values = months.map((month) => month.et0).filter(Number.isFinite)
  const hasData = temperatures.length > 0 || precipitation.length > 0

  if (!hasData) {
    return (
      <div className="card">
        <h2>NASA POWER monthly climate</h2>
        <p className="sub">No monthly values are available for {year}; synthetic values are not plotted.</p>
      </div>
    )
  }

  const width = 720
  const height = 230
  const left = 46
  const right = 42
  const top = 18
  const bottom = 34
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const slotWidth = plotWidth / months.length
  const baseY = top + plotHeight
  const maxWaterDepth = Math.max(
    1,
    Math.ceil(Math.max(0, ...precipitation, ...et0Values) / 10) * 10
  )
  const minTemperature = temperatures.length
    ? Math.floor(Math.min(...temperatures) - 1)
    : 0
  const maxTemperature = temperatures.length
    ? Math.ceil(Math.max(...temperatures) + 1)
    : 1
  const temperatureRange = Math.max(1, maxTemperature - minTemperature)
  let temperaturePath = ''
  let startTemperatureSegment = true
  months.forEach((month, index) => {
    if (!Number.isFinite(month.temperature)) {
      startTemperatureSegment = true
      return
    }
    const x = left + (index + 0.5) * slotWidth
    const y = top + ((maxTemperature - month.temperature) / temperatureRange) * plotHeight
    temperaturePath += `${startTemperatureSegment ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)} `
    startTemperatureSegment = false
  })
  let et0Path = ''
  let startEt0Segment = true
  months.forEach((month, index) => {
    if (!Number.isFinite(month.et0)) {
      startEt0Segment = true
      return
    }
    const x = left + (index + 0.5) * slotWidth
    const y = baseY - (month.et0 / maxWaterDepth) * plotHeight
    et0Path += `${startEt0Segment ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)} `
    startEt0Segment = false
  })
  const tempCoverage = nasaData.source_status?.temp_mean_c?.coverage_fraction
  const rainCoverage = nasaData.source_status?.rainfall_mm_tot?.coverage_fraction
  const et0Coverage = nasaData.source_status?.et0?.coverage_fraction
  const coverageNote = Number.isFinite(tempCoverage) && Number.isFinite(rainCoverage)
    ? `Daily coverage over the full window: T2M ${(tempCoverage * 100).toFixed(1)}%, precipitation ${(rainCoverage * 100).toFixed(1)}%.${Number.isFinite(et0Coverage) ? ` Complete FAO-56 ET0 days: ${(et0Coverage * 100).toFixed(1)}%.` : ''}`
    : 'Daily coverage is reported for the full observation window.'

  return (
    <div className="card power-chart">
      <div className="power-chart-header">
        <div>
          <h2>NASA POWER monthly climate</h2>
          <p className="sub">Monthly mean air temperature and precipitation total for the selected year.</p>
        </div>
        <label className="power-chart-year">
          Year
          <select value={year} onChange={(event) => setSelectedYear(event.target.value)}>
            {years.map((availableYear) => (
              <option key={availableYear} value={availableYear}>{availableYear}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="power-chart-scroll">
        <svg
          className="power-chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`NASA POWER monthly air temperature, precipitation${et0Values.length ? ' and reference evapotranspiration' : ''} for ${year}`}
        >
          <title>NASA POWER monthly climate and reference evapotranspiration, {year}</title>
          {[0, 0.5, 1].map((fraction) => {
            const y = top + fraction * plotHeight
            const rainValue = Math.round(maxWaterDepth * (1 - fraction))
            const tempValue = Math.round(maxTemperature - fraction * temperatureRange)
            return (
              <g key={fraction}>
                <line x1={left} x2={width - right} y1={y} y2={y} stroke="#e2e8f0" />
                <text x={left - 7} y={y + 4} textAnchor="end" className="power-chart-axis">
                  {rainValue}
                </text>
                {temperatures.length > 0 && (
                  <text x={width - right + 7} y={y + 4} className="power-chart-axis">
                    {tempValue}°
                  </text>
                )}
              </g>
            )
          })}
          {months.map((month, index) => {
            if (!Number.isFinite(month.precipitation)) return null
            const barHeight = (month.precipitation / maxWaterDepth) * plotHeight
            const x = left + (index + 0.5) * slotWidth
            return (
              <rect
                key={month.label}
                x={x - slotWidth * 0.28}
                y={baseY - barHeight}
                width={slotWidth * 0.56}
                height={barHeight}
                rx="2"
                fill="#7bbbd0"
              >
                <title>{month.label}: {month.precipitation.toFixed(1)} mm precipitation</title>
              </rect>
            )
          })}
          {et0Path && (
            <path
              d={et0Path}
              fill="none"
              stroke="#d88c1b"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}
          {temperaturePath && (
            <path
              d={temperaturePath}
              fill="none"
              stroke="#0b6e4f"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}
          {months.map((month, index) => {
            if (!Number.isFinite(month.temperature)) return null
            const x = left + (index + 0.5) * slotWidth
            const y = top + ((maxTemperature - month.temperature) / temperatureRange) * plotHeight
            return (
              <circle key={month.label} cx={x} cy={y} r="3.5" fill="#fff" stroke="#0b6e4f" strokeWidth="2">
                <title>{month.label}: {month.temperature.toFixed(1)} °C mean air temperature</title>
              </circle>
            )
          })}
          {months.map((month, index) => {
            if (!Number.isFinite(month.et0)) return null
            const x = left + (index + 0.5) * slotWidth
            const y = baseY - (month.et0 / maxWaterDepth) * plotHeight
            return (
              <circle key={`${month.label}-et0`} cx={x} cy={y} r="3.5" fill="#fff" stroke="#d88c1b" strokeWidth="2">
                <title>{month.label}: {month.et0.toFixed(1)} mm reference ET0</title>
              </circle>
            )
          })}
          {months.map((month, index) => (
            <text
              key={month.label}
              x={left + (index + 0.5) * slotWidth}
              y={height - 8}
              textAnchor="middle"
              className="power-chart-axis"
            >
              {month.label}
            </text>
          ))}
        </svg>
      </div>
      <div className="power-chart-legend">
        <span><i className="power-chart-swatch precipitation" /> Precipitation (mm/month) · PRECTOTCORR</span>
        {et0Values.length > 0 && <span><i className="power-chart-swatch et0" /> Reference ET0 (mm/month) · FAO-56</span>}
        <span><i className="power-chart-swatch temperature" /> Air temperature (°C) · T2M</span>
      </div>
      <p className="sub power-chart-note">{coverageNote} NASA POWER gridded estimates, not field-sensor measurements. ET0 refers to a standardized grass surface, not crop-specific water use.</p>
    </div>
  )
}

// ---- Map component ----
function FieldMap({ field, regionBoundaries, onCoordinateSelect }) {
  useEffect(() => {
    const container = document.getElementById('field-map')
    if (!container) return
    const map = L.map(container).setView(
      field ? [field.lat, field.lon] : [31.8, -6.0],
      field ? 8 : 5
    )
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    }).addTo(map)
    let boundaryLayer = null
    if (regionBoundaries) {
      boundaryLayer = L.geoJSON(regionBoundaries, {
        style: {
          color: '#286c58',
          weight: 1.6,
          opacity: 0.9,
          fillColor: '#4b9279',
          fillOpacity: 0.06,
        },
        onEachFeature: (feature, layer) => {
          const { region_code: regionCode, region_name: regionName } = feature.properties
          layer.bindTooltip(regionName, { sticky: true })
          layer.on('click', (event) => {
            L.DomEvent.stopPropagation(event)
            onCoordinateSelect({
              lat: Number(event.latlng.lat.toFixed(5)),
              lon: Number(event.latlng.lng.toFixed(5)),
              regionCode,
            })
          })
        },
      }).addTo(map)
    }
    if (!field && boundaryLayer?.getBounds().isValid()) {
      map.fitBounds(boundaryLayer.getBounds(), { padding: [12, 12] })
    }
    map.on('click', (event) => {
      onCoordinateSelect({
        lat: Number(event.latlng.lat.toFixed(5)),
        lon: Number(event.latlng.lng.toFixed(5)),
      })
    })
    if (field) {
      L.marker([field.lat, field.lon])
        .addTo(map)
        .bindPopup(`<b>${field.region_name}</b><br>${field.area_ha} ha · ${field.irrigation}`)
    }
    return () => map.remove()
  }, [field, regionBoundaries, onCoordinateSelect])

  return (
    <div className="map-section">
      <div id="field-map" className="map-wrap" aria-label="Map of Morocco; click to select field coordinates" />
      <p className="map-hint">Click a region to select it and set the field point, or click elsewhere on the map to set coordinates. The selected region is verified when you apply the location.</p>
    </div>
  )
}

async function demoSeed() {
  return api('/api/demo/seed.json')
}

// ---- Main App ----
export default function App() {
  const [field, setField] = useState(null)
  const [draftField, setDraftField] = useState(DEFAULT_FIELD_DRAFT)
  const [regions, setRegions] = useState([])
  const [regionSource, setRegionSource] = useState(null)
  const [regionBoundaries, setRegionBoundaries] = useState(null)
  const [cropCatalog, setCropCatalog] = useState({ crops: [], sources: [], policy: '' })
  const [catalogFilter, setCatalogFilter] = useState('all')
  const [fieldError, setFieldError] = useState(null)
  const [fieldValidationLoading, setFieldValidationLoading] = useState(false)
  const [scenarios, setScenarios] = useState([])
  const [priorities, setPriorities] = useState({ water: 0.2, nitrogen: 0.15, resilience: 0.25, soil: 0.2, economy: 0.2 })
  const [crops, setCrops] = useState(DEFAULT_CROPS)
  const [activeScenario, setActiveScenario] = useState('historical')
  const [comparison, setComparison] = useState(null)
  const [comparisonError, setComparisonError] = useState(null)
  const [comparing, setComparing] = useState(false)
  const [nasaData, setNasaData] = useState(null)
  const [nasaError, setNasaError] = useState(null)
  const [nasaLoading, setNasaLoading] = useState(false)
  const [appError, setAppError] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadDemo = useCallback(async () => {
    const [seed, regionResponse, cropResponse, boundaryResponse] = await Promise.all([
      demoSeed(),
      api('/api/regions'),
      api('/api/crops'),
      api('/api/regions/boundaries'),
    ])
    setRegions(regionResponse.regions)
    setRegionSource({
      ...regionResponse.source,
      boundary_source: regionResponse.boundary_source,
    })
    setRegionBoundaries(boundaryResponse)
    setCropCatalog(cropResponse)
    setScenarios(seed.scenarios)
    setPriorities(seed.priorities)
    setCrops(seed.current_rotation || DEFAULT_CROPS)
  }, [])

  useEffect(() => {
    loadDemo()
      .catch((error) => setAppError(error.message))
      .finally(() => setLoading(false))
  }, [loadDemo])

  const handleMapCoordinateSelect = useCallback(({ lat, lon, regionCode }) => {
    setDraftField((current) => ({
      ...current,
      lat: String(lat),
      lon: String(lon),
      ...(regionCode ? { region_code: regionCode } : {}),
    }))
    setFieldError(null)
  }, [])

  async function useSelectedField(event) {
    event.preventDefault()
    const lat = Number(draftField.lat)
    const lon = Number(draftField.lon)
    const areaHa = Number(draftField.area_ha)
    const region = regions.find((item) => item.code === draftField.region_code)
    if (!region || !Number.isFinite(lat) || lat < 20 || lat > 37 ||
        !Number.isFinite(lon) || lon < -18 || lon > 0) {
      setFieldError('Choose a region and coordinates within Morocco.')
      return
    }
    if (!Number.isFinite(areaHa) || areaHa <= 0) {
      setFieldError('Enter a farm area greater than zero hectares.')
      return
    }

    const textureKeys = ['sand_pct', 'silt_pct', 'clay_pct']
    const suppliedTextureKeys = textureKeys.filter((key) => draftField[key] !== '')
    if (suppliedTextureKeys.length > 0 && suppliedTextureKeys.length !== textureKeys.length) {
      setFieldError('Enter all three soil texture percentages, or leave all three blank.')
      return
    }
    if (suppliedTextureKeys.length === textureKeys.length) {
      const textureTotal = textureKeys.reduce(
        (total, key) => total + Number(draftField[key]),
        0
      )
      if (Math.abs(textureTotal - 100) > 3) {
        setFieldError('Sand, silt, and clay percentages must total 100%.')
        return
      }
    }
    const soilRanges = {
      sand_pct: [0, 100],
      silt_pct: [0, 100],
      clay_pct: [0, 100],
      ph: [0, 14],
      organic_c_pct: [0, 100],
      nacl_ppth: [0, 1000],
    }
    for (const [key, [minimum, maximum]] of Object.entries(soilRanges)) {
      if (draftField[key] === '') continue
      const value = Number(draftField[key])
      if (!Number.isFinite(value) || value < minimum || value > maximum) {
        setFieldError(`${key.replaceAll('_', ' ')} must be between ${minimum} and ${maximum}.`)
        return
      }
    }

    let location
    setFieldValidationLoading(true)
    try {
      location = await api(
        `/api/regions/locate?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`
      )
    } catch (error) {
      setFieldError(error.message)
      return
    } finally {
      setFieldValidationLoading(false)
    }
    if (!location.region_codes.includes(region.code)) {
      const matchingNames = location.regions.map((item) => item.name).join(' / ')
      setFieldError(
        `Coordinates are in ${matchingNames}, not ${region.name}. Choose a matching region or change the coordinates.`
      )
      return
    }

    const soil = {}
    if (draftField.soil_type) soil.soil_type = draftField.soil_type
    for (const key of ['sand_pct', 'silt_pct', 'clay_pct', 'ph', 'organic_c_pct', 'nacl_ppth']) {
      if (draftField[key] !== '') soil[key] = Number(draftField[key])
    }
    setField({
      region_code: region.code,
      region_name: region.name,
      lat,
      lon,
      area_ha: areaHa,
      irrigation: draftField.irrigation,
      soil: Object.keys(soil).length ? soil : null,
    })
    setFieldError(null)
    setComparison(null)
  }

  // Re-evaluate the user's reference rotation and priorities when they change.
  useEffect(() => {
    if (!field || scenarios.length === 0) {
      setNasaData(null)
      setNasaError(null)
      return
    }
    let cancelled = false
    async function run() {
      setComparing(true)
      setComparisonError(null)
      setNasaLoading(true)
      setNasaError(null)
      try {
        const comp = await api('/api/compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            crops,
            priorities,
            field: {
              region_code: field.region_code,
              lat: field.lat,
              lon: field.lon,
              area_ha: field.area_ha,
              irrigation: field.irrigation,
              soil: field.soil,
            },
          }),
        })
        if (!cancelled) {
          setComparison(comp)
          setNasaData(comp.nasa)
        }
      } catch (error) {
        if (!cancelled) {
          setComparison(null)
          setComparisonError(error.message)
          setNasaError(error.message)
        }
      } finally {
        if (!cancelled) {
          setComparing(false)
          setNasaLoading(false)
        }
      }
    }
    run()
    return () => { cancelled = true }
  }, [field, scenarios, priorities, crops])

  if (loading) {
    return (
      <div className="app">
        <div className="card" style={{ textAlign: 'center', padding: '40px' }}>Loading NEX TERRA…</div>
      </div>
    )
  }
  if (appError) {
    return (
      <div className="app">
        <div className="card error-message" role="alert">
          Could not load NEX TERRA configuration: {appError}
        </div>
      </div>
    )
  }
  const sc = scenarios.find(s => s.id === activeScenario) || scenarios[0]
    const comparisonA = comparison
    const activeRows = comparisonA
      ? comparisonA.comparison.filter(c => c.scenario_id === activeScenario)
      : []
    const activeComp = [...activeRows].sort((a, b) => b.score - a.score)[0]
    const waterText = activeComp ? activeComp.water_total_mm.toFixed(0) : '—'
    const resilienceText = activeComp ? ((activeComp.resilience_avg || 0) * 100).toFixed(0) : '—'
    const rotationCrops = cropCatalog.crops.filter(crop => crop.rotation_eligible)
    const catalogCrops = cropCatalog.crops.filter(crop =>
      catalogFilter === 'all' || crop.life_cycle === catalogFilter
    )
    const cropSources = Object.fromEntries(
      cropCatalog.sources.map(source => [source.id, source])
    )

  return (
    <div className="app">
      <header className="header">
        <h1>NEX TERRA — Farm Rotation Decision Support</h1>
        <p>Explore crop-rotation strategies for a farm anywhere in Morocco using NASA climate data and clear evidence limits.</p>
        <span className="tagline">Morocco · 12 administrative regions</span>
      </header>

      <div className="layout">
        <div>
          <form className="card field-selector" onSubmit={useSelectedField}>
            <h2>Set up your farm</h2>
            <p className="sub">Choose an administrative region, click its map boundary to select it, or enter field coordinates.</p>
            <label>
              Administrative region
              <select
                required
                value={draftField.region_code}
                onChange={(event) => setDraftField((current) => ({
                  ...current,
                  region_code: event.target.value,
                }))}
              >
                <option value="">Select a region</option>
                {regions.map((region) => (
                  <option key={region.code} value={region.code}>{region.name}</option>
                ))}
              </select>
            </label>
            <div className="field-form-grid">
              <label>
                Latitude
                <input
                  required
                  type="number"
                  step="0.00001"
                  min="20"
                  max="37"
                  value={draftField.lat}
                  onChange={(event) => setDraftField((current) => ({ ...current, lat: event.target.value }))}
                />
              </label>
              <label>
                Longitude
                <input
                  required
                  type="number"
                  step="0.00001"
                  min="-18"
                  max="0"
                  value={draftField.lon}
                  onChange={(event) => setDraftField((current) => ({ ...current, lon: event.target.value }))}
                />
              </label>
              <label>
                Farm area (ha)
                <input
                  required
                  type="number"
                  min="0.01"
                  max="100000"
                  step="0.01"
                  value={draftField.area_ha}
                  onChange={(event) => setDraftField((current) => ({ ...current, area_ha: event.target.value }))}
                />
              </label>
              <label>
                Irrigation
                <select
                  value={draftField.irrigation}
                  onChange={(event) => setDraftField((current) => ({
                    ...current,
                    irrigation: event.target.value,
                  }))}
                >
                  <option value="unknown">Unknown</option>
                  <option value="rainfed">Rainfed</option>
                  <option value="irrigated">Irrigated</option>
                  <option value="mixed">Mixed</option>
                </select>
              </label>
            </div>
            <details className="soil-entry">
              <summary>Optional local soil measurements</summary>
              <p className="sub">Leave unknown values blank. Values entered here are treated as farmer-provided, not satellite measurements.</p>
              <label>
                Soil texture
                <select
                  value={draftField.soil_type}
                  onChange={(event) => setDraftField((current) => ({
                    ...current,
                    soil_type: event.target.value,
                  }))}
                >
                  <option value="">Unknown</option>
                  <option value="sand">Sand</option>
                  <option value="loamy_sand">Loamy sand</option>
                  <option value="loam">Loam</option>
                  <option value="silt_loam">Silt loam</option>
                  <option value="clay">Clay</option>
                </select>
              </label>
              <div className="field-form-grid">
                {[
                  ['sand_pct', 'Sand (%)'],
                  ['silt_pct', 'Silt (%)'],
                  ['clay_pct', 'Clay (%)'],
                  ['ph', 'pH'],
                  ['organic_c_pct', 'Organic carbon (%)'],
                  ['nacl_ppth', 'Salinity (g/kg)'],
                ].map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      step="0.1"
                      value={draftField[key]}
                      onChange={(event) => setDraftField((current) => ({
                        ...current,
                        [key]: event.target.value,
                      }))}
                    />
                  </label>
                ))}
              </div>
            </details>
            {fieldError && <p className="error-message" role="alert">{fieldError}</p>}
            <button
              type="submit"
              className="primary-button"
              disabled={fieldValidationLoading}
            >
              {fieldValidationLoading ? 'Verifying administrative region...' : 'Use this farm location'}
            </button>
            <p className="sub field-data-note">
              Coordinates are checked against mapped 2017 administrative-region boundaries; points outside mapped regions are rejected.
            </p>
            {regionSource?.url && (
              <p className="sub field-data-note">
                Region reference: <a href={regionSource.url} target="_blank" rel="noreferrer">Morocco Directorate General of Local Authorities</a>
              </p>
            )}
            {regionSource?.boundary_source && (
              <p className="sub field-data-note">
                Boundary data: <a href={regionSource.boundary_source.url} target="_blank" rel="noreferrer">
                  {regionSource.boundary_source.name} ({regionSource.boundary_source.year}; {regionSource.boundary_source.license})
                </a>. Boundaries are generalized; a point on a shared edge may match both regions.
              </p>
            )}
          </form>

          <FieldMap
            field={field}
            regionBoundaries={regionBoundaries}
            onCoordinateSelect={handleMapCoordinateSelect}
          />
          <section className="card crop-catalog">
            <h2>Morocco crop catalog</h2>
            <p className="sub">{cropCatalog.policy}</p>
            <label>
              Show
              <select value={catalogFilter} onChange={event => setCatalogFilter(event.target.value)}>
                <option value="all">All catalog entries</option>
                <option value="annual">Annual crops</option>
                <option value="perennial">Perennial crops</option>
                <option value="mixed">Crop groups and other entries</option>
              </select>
            </label>
            <div className="crop-catalog-list">
              {catalogCrops.map(crop => {
                const documentedRegions = crop.documented_regions
                  .map(code => regions.find(region => region.code === code)?.name)
                  .filter(Boolean)
                return (
                  <article className="crop-catalog-item" key={crop.code}>
                    <div className="crop-catalog-heading">
                      <strong>{crop.name}</strong>
                      <span>{crop.life_cycle.replaceAll('_', ' ')}</span>
                    </div>
                    <p className="sub">
                      {crop.national_status === 'documented'
                        ? 'Nationally documented'
                        : crop.national_status === 'group_only'
                          ? 'Evidence applies to a crop group or related type'
                          : crop.national_status === 'not_applicable'
                            ? 'Not a crop species'
                            : 'National presence not verified'}
                      {' · '}
                      {crop.rotation_eligible
                        ? 'Annual rotation option; prototype scores are unvalidated'
                        : 'Catalog only; excluded from annual rotations'}
                    </p>
                    <p className="sub">{crop.evidence_note}</p>
                    <p className="sub">
                      Administrative-region evidence:{' '}
                      {documentedRegions.length
                        ? documentedRegions.join(', ')
                        : 'unknown from the cited sources'}
                    </p>
                    {crop.geographic_note && <p className="sub">{crop.geographic_note}</p>}
                    <p className="sub crop-source-links">
                      {crop.source_ids.length
                        ? crop.source_ids.map(sourceId => {
                          const source = cropSources[sourceId]
                          return source && (
                            <a key={sourceId} href={source.url} target="_blank" rel="noreferrer">
                              {source.title}
                            </a>
                          )
                        })
                        : 'No national crop source verified yet.'}
                    </p>
                  </article>
                )
              })}
            </div>
          </section>
          {field && (
            <div className="card">
              <h2>Selected farm</h2>
              <p className="sub">{field.region_name} · {field.area_ha} ha · {field.irrigation}</p>
              <p className="sub">Field point: {field.lat.toFixed(5)}, {field.lon.toFixed(5)}</p>
              <p className="sub">
                {field.soil
                  ? 'Soil measurements supplied by the user. Unentered properties still use prototype defaults.'
                  : 'No local soil measurements supplied; soil-related scores use prototype assumptions, not measured field data.'}
              </p>
            </div>
          )}
        </div>

        <div>
          {!field ? (
            <div className="card">
              <h2>Start with your farm location</h2>
              <p className="sub">Select one of Morocco's 12 administrative regions and set a field point to load NASA POWER data for that location.</p>
              <p className="sub">Rotation comparisons will appear after a field is selected. Unknown regional crop calendars and soil values will not be invented.</p>
            </div>
          ) : (
          <div className="card">
            <h2>How do rotation scores compare across climate scenarios?</h2>
            <p className="sub">Compare your reference rotation with two illustrative alternatives. These prototype results are not region-specific crop recommendations.</p>

            <div className="card" style={{ padding: '0 0 14px 0' }}>
            <label className="slider-label">Illustrative stress-test scenario</label>
              <input
                type="range"
                min={0}
                max={scenarios.length - 1}
                value={scenarios.findIndex(s => s.id === activeScenario)}
                onChange={e => setActiveScenario(scenarios[e.target.value].id)}
                className="scenario-slider"
              />
              <div className="rotation-inputs">
                <strong>Reference rotation (one crop per season)</strong>
                <span className="sub">Only annual crops supported by the prototype are selectable. Each option’s evidence status is shown in the crop catalog.</span>
                {crops.map((crop, index) => (
                  <label key={index}>
                    Season {index + 1}
                    <select
                      value={crop}
                      onChange={event => setCrops(current =>
                        current.map((item, cropIndex) =>
                          cropIndex === index ? event.target.value : item
                        )
                      )}
                    >
                      {rotationCrops.map(crop => (
                        <option key={crop.code} value={crop.code}>
                          {crop.name}
                          {crop.national_status === 'unverified' ? ' — source not verified' : ''}
                          {crop.national_status === 'group_only' ? ' — group evidence only' : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <div className="priorities">
                {Object.entries(PRIORITY_LABELS).map(([key, label]) => (
                  <label key={key} className="priority-control">
                    <span>{label} <strong>{Math.round((priorities[key] || 0) * 100)}%</strong></span>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={priorities[key] || 0}
                      onChange={event => setPriorities(current => ({
                        ...current,
                        [key]: Number(event.target.value),
                      }))}
                    />
                  </label>
                ))}
              </div>
              <div className="sub">Priority values are normalized by the model before scoring. Scenario shifts and crop coefficients are illustrative, not regionally validated.</div>
              <div className="future-banner">
                <p><strong>{activeScenario.replace(/_/g, ' ')}</strong></p>
                <p>+{sc.temp_shift.toFixed(1)}°C warming · precipitation {sc.precipitation >= 1 ? '+' : ''}{Math.round((sc.precipitation - 1) * 100)}% · drought index {sc.drought.toFixed(2)}</p>
                <div className="impacts">
                  <span className="impact">water {waterText} mm</span>
                  <span className="impact">resilience {resilienceText}%</span>
                </div>
              </div>
              {nasaLoading && <p className="sub">Loading NASA POWER data for this field location…</p>}
              {nasaError && <p className="error-message" role="alert">NASA POWER request failed: {nasaError}</p>}
              {nasaData && (
                <>
                  <div className="card" style={{ padding: '12px 14px', background: '#f4faf6' }}>
                    <div className="sub" style={{ fontWeight: 700, marginBottom: 6 }}>
                      {nasaData.data_status === 'partial'
                        ? 'NASA POWER daily estimates + synthetic placeholders'
                        : 'Synthetic demo values — NASA POWER unavailable'}
                    </div>
                    <div className="sub"><b>Mean air temperature:</b> {nasaData.temp_mean_c.toFixed(2)} °C ({sourceLabel(nasaData.source_status?.temp_mean_c)}) · <b>Precipitation total:</b> {nasaData.rainfall_mm_tot.toFixed(1)} mm ({sourceLabel(nasaData.source_status?.rainfall_mm_tot)})</div>
                    <div className="sub"><b>Relative humidity:</b> {nasaData.humidity_pct.toFixed(0)}% ({sourceLabel(nasaData.source_status?.humidity_pct)}) · <b>Solar radiation:</b> {Number.isFinite(nasaData.solar_radiation_mj_m2_day) ? `${nasaData.solar_radiation_mj_m2_day.toFixed(1)} MJ/m²/day` : 'unavailable'} ({sourceLabel(nasaData.source_status?.solar_radiation_mj_m2_day)}) · <b>Wind:</b> {Number.isFinite(nasaData.wind_mean_ms) ? `${nasaData.wind_mean_ms.toFixed(1)} m/s` : 'unavailable'} ({sourceLabel(nasaData.source_status?.wind_mean_ms)})</div>
                    <div className="sub"><b>Reference ET0:</b> {Number.isFinite(nasaData.et0_mean_mm_day) ? `${nasaData.et0_mean_mm_day.toFixed(2)} mm/day` : 'unavailable'} ({sourceLabel(nasaData.source_status?.et0)}) · {Number.isFinite(nasaData.elevation_m) ? `${nasaData.elevation_m.toFixed(0)} m site elevation` : 'site elevation unavailable'}</div>
                    <div className="sub"><b>Vegetation (EVI):</b> {nasaData.evi.toFixed(3)} ({sourceLabel(nasaData.source_status?.evi)}) · <b>Soil moisture:</b> {nasaData.sm.toFixed(3)} ({sourceLabel(nasaData.source_status?.sm)}) · <b>Future warming:</b> +{nasaData.cmip6?.temp_mean_c?.toFixed(1) || '—'}°C ({sourceLabel(nasaData.source_status?.cmip6)})</div>
                    <div className="sub">{Number.isFinite(nasaData.lat) ? nasaData.lat.toFixed(3) : '—'}, {Number.isFinite(nasaData.lon) ? nasaData.lon.toFixed(3) : '—'} · {nasaData.observed_window_years?.join('–') || 'period unavailable'} · Values are gridded estimates, not field-sensor measurements.</div>
                    <div className="sub" style={{ fontSize: 12, color: '#4a5c74' }}>{nasaData.source_note || 'Data provenance is not supplied.'}</div>
                  </div>
                  {nasaData.data_status === 'partial' && <PowerMonthlyChart nasaData={nasaData} />}
                </>
              )}
            </div>

            {comparisonError && <p className="error-message">Comparison unavailable: {comparisonError}</p>}
            {comparing && <p className="sub">Recalculating the comparison…</p>}
            {comparisonA && (
              <>
                <section className="comparison-context" aria-label="How to interpret this comparison">
                  <h3>Prototype comparison — not a crop recommendation</h3>
                  <p>{comparisonA.comparison_context.score_explanation}</p>
                  <p>{comparisonA.comparison_context.nasa_role}</p>
                  <p><strong>Field soil input:</strong> {comparisonA.comparison_context.field_soil_status}. <strong>NASA POWER status:</strong> {comparisonA.comparison_context.nasa_data_status}.</p>
                  <div className="comparison-context-grid">
                    <div>
                      <strong>What the score uses</strong>
                      <ul>
                        {comparisonA.comparison_context.score_inputs.map(item => <li key={item}>{item}</li>)}
                      </ul>
                    </div>
                    <div>
                      <strong>Known gaps and risks</strong>
                      <ul>
                        {comparisonA.comparison_context.data_gaps.map(item => <li key={item}>{item}</li>)}
                      </ul>
                    </div>
                  </div>
                </section>
                <div className="sub" style={{ marginBottom: 8 }}>
                  Cross-scenario rank is based on mean prototype score across all scenarios; the table shows metrics for the selected scenario.
                </div>
                <div className="comp-table-wrap">
                  <table className="comp-table">
                    <thead><tr>
                      <th>Cross-scenario rank</th><th>Strategy in selected scenario</th><th>Crops</th><th>Prototype water demand (mm)</th><th>Prototype N balance (kg/ha)</th><th>Modelled resilience</th><th>Modelled soil protection</th><th>Prototype gross revenue assumption (MAD/ha)</th><th>Prototype score</th>
                    </tr></thead>
                    <tbody>
                      {activeRows.map(c => (
                        <tr key={`${c.scenario_id}-${c.strategy_id}`}>
                          <td><RankBadge rank={comparisonA.ranked.find(item => item.id === c.strategy_id)?.rank} /></td>
                          <td><strong>{c.strategy_label}</strong></td>
                          <td>{c.rotation.join(' · ')}</td>
                          <td>{c.water_total_mm.toFixed(0)}</td>
                          <td>{c.n_balance_kg.toFixed(1)}</td>
                          <td>{(c.resilience_avg * 100).toFixed(0)}%</td>
                          <td>{(c.soil_protection_avg * 100).toFixed(0)}%</td>
                          <td>{c.economic_potential_avg.toFixed(0)}</td>
                          <td>{c.score.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="sub" style={{ marginTop: 14, marginBottom: 6 }}>Highest prototype score in this scenario (not a recommendation): <strong>{activeComp?.strategy_label || '—'}</strong></div>

                <div className="explanations">
                  {(comparisonA.strategies || []).map(strategy => (
                    <div className="expl" key={strategy.id}>
                      <h3>{strategy.label}</h3>
                      <p>{strategy.rationale}</p>
                      <p><strong>Crop evidence and availability:</strong></p>
                      <ul className="strategy-crop-evidence">
                        {strategy.crop_evidence.map((crop, index) => {
                          const documentedRegions = crop.documented_regions
                            .map(code => regions.find(region => region.code === code)?.name)
                            .filter(Boolean)
                          return (
                            <li key={`${crop.code}-${index}`}>
                              <strong>{crop.name}</strong> — {crop.national_status === 'documented'
                                ? 'nationally documented'
                                : crop.national_status === 'group_only'
                                  ? 'group-level evidence only'
                                  : 'national presence not verified'}
                              . {crop.evidence_note}
                              {' '}
                              {documentedRegions.length
                                ? `Named regions: ${documentedRegions.join(', ')}.`
                                : 'Region-specific availability is unknown.'}
                              {crop.source_ids.map(sourceId => {
                                const source = cropSources[sourceId]
                                return source && (
                                  <a key={sourceId} href={source.url} target="_blank" rel="noreferrer">
                                    {' '}{source.title}
                                  </a>
                                )
                              })}
                            </li>
                          )
                        })}
                      </ul>
                      <p><strong>Strategy-specific risks and limitations:</strong> {strategy.limitations.join(' ')}</p>
                      {strategy.data_gaps.length > 0 && (
                        <div>
                          <strong>Strategy-specific data gaps:</strong>
                          <ul>{strategy.data_gaps.map(item => <li key={item}>{item}</li>)}</ul>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

              </>
            )}
          </div>
          )}
        </div>
      </div>
    </div>
  )
}
