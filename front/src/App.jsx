import { useEffect, useState, useCallback, useRef } from 'react'
import L from 'leaflet'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import FarmAccountPanel from './FarmAccountPanel'
import SimulationHistoryPanel from './SimulationHistoryPanel'

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
const OBSERVED_FIELD_ISSUES = [
  'Visible soil erosion',
  'Salt crust or suspected salinity',
  'Waterlogging or poor drainage',
  'Compacted soil',
  'Low plant cover',
  'Pest or disease symptoms',
  'Other observed issue',
]
const PAGE_FLOW = [
  { key: 'home', path: '/', label: 'Home' },
  { key: 'about', path: '/about', label: 'About' },
  { key: 'data', path: '/data', label: 'Agricultural Data' },
  { key: 'simulation', path: '/simulation', label: 'Simulation' },
  { key: 'results', path: '/results', label: 'Results' },
  { key: 'methodology', path: '/methodology', label: 'Methodology' },
  { key: 'team', path: '/team', label: 'Team' },
]

function createFarmAssessment() {
  return {
    crops: Array.from({ length: 3 }, () => ({
      name: '',
      sowing_date: '',
      harvest_date: '',
      yield_t_ha: '',
      yield_year: '',
      yield_source: 'unknown',
    })),
    irrigation_source: 'unknown',
    irrigation_method: 'unknown',
    water_availability: 'unknown',
    soil_source: 'unknown',
    soil_sample_date: '',
    fertilizer_name: '',
    fertilizer_rate: '',
    organic_inputs: '',
    observed_issues: [],
    observation_notes: '',
  }
}

function normalizeFarmAssessment(value) {
  const empty = createFarmAssessment()
  if (!value || typeof value !== 'object' || Array.isArray(value)) return empty
  const savedCrops = Array.isArray(value.crops) ? value.crops : []
  return {
    ...empty,
    ...value,
    crops: empty.crops.map((crop, index) => ({
      ...crop,
      ...(savedCrops[index] && typeof savedCrops[index] === 'object'
        ? savedCrops[index]
        : {}),
    })),
    observed_issues: Array.isArray(value.observed_issues)
      ? value.observed_issues.filter((issue) => typeof issue === 'string')
      : empty.observed_issues,
  }
}

// ---- helpers ----
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, '') || ''

async function api(path, opts) {
  const res = await fetch(`${API_BASE_URL}${path}`, opts)
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

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 56 56" aria-hidden="true" focusable="false">
      <path d="M28 4 50 16.5 28 29 6 16.5Z" fill="#d9b875" />
      <path d="M6 16.5 28 29v23L6 39.5Z" fill="#27684f" />
      <path d="M50 16.5 28 29v23l22-12.5Z" fill="#123d33" />
      <path d="M14 21 28 29l14-8" fill="none" stroke="#f4e3ba" strokeOpacity=".7" strokeWidth="1.2" />
      <path d="m9 25 17 9.7m-17-3.8 17 9.7m-17-3.8 17 9.7" fill="none" stroke="#d7e4c9" strokeOpacity=".75" strokeWidth="1" />
      <path d="m30 34.7 17-9.7m-17 15.6 17-9.7m-17 15.6 17-9.7" fill="none" stroke="#b6cfb8" strokeOpacity=".72" strokeWidth="1" />
      <path d="M28 18v-8" fill="none" stroke="#194d3b" strokeLinecap="round" strokeWidth="1.6" />
      <path d="M28 15c-5.2-6.1-9-5.1-10.1-4.1 1 4.9 5.2 7.3 10.1 6.5" fill="#f3e5c4" />
      <path d="M28 13.3c3.4-6.6 7.6-7.3 10.1-6.1-.2 5.1-3.2 8.3-10.1 9.7" fill="#f8f2df" />
      <path d="M28 15c-5.2-6.1-9-5.1-10.1-4.1 1 4.9 5.2 7.3 10.1 6.5m0-4.1c3.4-6.6 7.6-7.3 10.1-6.1-.2 5.1-3.2 8.3-10.1 9.7" fill="none" stroke="#fff9e9" strokeLinejoin="round" strokeWidth=".8" />
    </svg>
  )
}

function BrandLockup({ className = '', ...props }) {
  return (
    <Link to="/" className={`brand-lockup ${className}`.trim()} aria-label="NEX TERRA home" {...props}>
      <BrandMark />
      <span className="brand-wordmark">NEX <strong>TERRA</strong></span>
    </Link>
  )
}

function PageStepNavigation({ currentPage }) {
  const index = PAGE_FLOW.findIndex((page) => page.key === currentPage)
  const previous = PAGE_FLOW[index - 1]
  const next = PAGE_FLOW[index + 1]
  return (
    <nav className="page-step-navigation" aria-label="Page sequence">
      {previous
        ? <Link className="step-previous" to={previous.path}>← {previous.label}</Link>
        : <span />}
      <span className="step-progress">Step {index + 1} of {PAGE_FLOW.length}</span>
      {next
        ? <Link className="step-next" to={next.path}>{next.label} <span aria-hidden="true">→</span></Link>
        : <span className="step-complete">End of the journey</span>}
    </nav>
  )
}

function ComparisonCharts({ rows }) {
  if (!rows.length) return null

  const maximumWater = Math.max(1, ...rows.map((row) => row.water_total_mm))
  const panels = [
    {
      id: 'water',
      title: 'Estimated water demand',
      note: 'Total across the modelled sequence · mm',
      scale: maximumWater,
      value: (row) => row.water_total_mm,
      format: (value) => `${value.toFixed(0)} mm`,
    },
    {
      id: 'resilience',
      title: 'Modelled resilience',
      note: 'Prototype index · 0 to 1',
      scale: 1,
      value: (row) => row.resilience_avg,
      format: (value) => `${(value * 100).toFixed(0)}%`,
    },
    {
      id: 'score',
      title: 'Weighted prototype score',
      note: 'Exploratory ranking metric · 0 to 1',
      scale: 1,
      value: (row) => row.score,
      format: (value) => value.toFixed(3),
    },
  ]

  return (
    <div className="results-charts" aria-label="Visual comparison of prototype rotation metrics">
      {panels.map((panel) => (
        <section className="results-chart" key={panel.id}>
          <div className="results-chart-heading">
            <h3>{panel.title}</h3>
            <span>{panel.note}</span>
          </div>
          {rows.map((row) => {
            const value = Number(panel.value(row)) || 0
            const width = Math.max(0, Math.min(100, (value / panel.scale) * 100))
            return (
              <div className="results-chart-row" key={`${panel.id}-${row.strategy_id}`}>
                <div className="results-chart-label">
                  <strong>{row.strategy_label}</strong>
                  <span>{panel.format(value)}</span>
                </div>
                <div
                  className="results-chart-track"
                  role="progressbar"
                  aria-label={`${row.strategy_label}: ${panel.format(value)}`}
                  aria-valuemin={0}
                  aria-valuemax={panel.scale}
                  aria-valuenow={value}
                >
                  <span style={{ width: `${width}%` }} />
                </div>
                <p>{row.rotation.join(' · ')}</p>
              </div>
            )
          })}
        </section>
      ))}
    </div>
  )
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
        <div className="workspace-column">
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
function FieldMap({ draftField, regionBoundaries, regions, onCoordinateSelect }) {
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const onCoordinateSelectRef = useRef(onCoordinateSelect)

  useEffect(() => {
    onCoordinateSelectRef.current = onCoordinateSelect
  }, [onCoordinateSelect])

  useEffect(() => {
    const container = document.getElementById('field-map')
    if (!container || !regionBoundaries) return
    const map = L.map(container).setView([31.8, -6.0], 5)
    mapRef.current = map
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
            const needsRefinement = map.getZoom() < 9
            onCoordinateSelectRef.current({
              lat: Number(event.latlng.lat.toFixed(5)),
              lon: Number(event.latlng.lng.toFixed(5)),
              regionCode,
              needsRefinement,
            })
            if (needsRefinement) map.flyTo(event.latlng, 9, { duration: 0.5 })
          })
        },
      }).addTo(map)
    }
    if (boundaryLayer?.getBounds().isValid()) {
      map.fitBounds(boundaryLayer.getBounds(), { padding: [12, 12] })
    }
    map.on('click', (event) => {
      onCoordinateSelectRef.current({
        lat: Number(event.latlng.lat.toFixed(5)),
        lon: Number(event.latlng.lng.toFixed(5)),
      })
    })
    return () => {
      markerRef.current?.remove()
      markerRef.current = null
      map.remove()
      mapRef.current = null
    }
  }, [regionBoundaries])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markerRef.current?.remove()
    markerRef.current = null
    const lat = Number(draftField.lat)
    const lon = Number(draftField.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
        draftField.lat === '' || draftField.lon === '') return

    const regionName = regions.find(
      (region) => region.code === draftField.region_code
    )?.name || 'Region not detected'
    markerRef.current = L.circleMarker([lat, lon], {
      radius: 8,
      color: '#ffffff',
      weight: 3,
      fillColor: '#0b6e4f',
      fillOpacity: 1,
    }).addTo(map)
    markerRef.current.bindTooltip(
      `${regionName} · ${lat.toFixed(5)}, ${lon.toFixed(5)}`
    )
  }, [draftField.lat, draftField.lon, draftField.region_code, regions])

  return (
    <div className="map-section">
      <div id="field-map" className="map-wrap" aria-label="Map of Morocco; click to select field coordinates" />
      <p className="map-hint">Choose a point on the map, or enter latitude and longitude below. Click again to refine the marker; the nearest named locality and administrative region are identified when available.</p>
    </div>
  )
}

async function demoSeed() {
  return api('/api/demo/seed.json')
}

// ---- Main App ----
export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const currentPage = PAGE_FLOW.find((page) => page.path === location.pathname)?.key || 'home'
  const [field, setField] = useState(null)
  const [draftField, setDraftField] = useState(DEFAULT_FIELD_DRAFT)
  const [regions, setRegions] = useState([])
  const [regionSource, setRegionSource] = useState(null)
  const [regionBoundaries, setRegionBoundaries] = useState(null)
  const [cropCatalog, setCropCatalog] = useState({ crops: [], sources: [], policy: '' })
  const [catalogFilter, setCatalogFilter] = useState('all')
  const [fieldError, setFieldError] = useState(null)
  const [fieldValidationLoading, setFieldValidationLoading] = useState(false)
  const [mapLocationStatus, setMapLocationStatus] = useState('idle')
  const [mapLocationMessage, setMapLocationMessage] = useState('')
  const [placeName, setPlaceName] = useState('')
  const [placeNameStatus, setPlaceNameStatus] = useState('idle')
  const mapSelectionRequest = useRef(0)
  const skipAssessmentResetRef = useRef(false)
  const [scenarios, setScenarios] = useState([])
  const [priorities, setPriorities] = useState({ water: 0.2, nitrogen: 0.15, resilience: 0.25, soil: 0.2, economy: 0.2 })
  const [includeCurrentRotation, setIncludeCurrentRotation] = useState(false)
  const [crops, setCrops] = useState(['', '', ''])
  const [farmAssessment, setFarmAssessment] = useState(createFarmAssessment)
  const [activeScenario, setActiveScenario] = useState('historical')
  const [simulationInput, setSimulationInput] = useState(null)
  const [comparison, setComparison] = useState(null)
  const skipNextSimulationRef = useRef(false)
  const [comparisonError, setComparisonError] = useState(null)
  const [comparing, setComparing] = useState(false)
  const [nasaData, setNasaData] = useState(null)
  const [nasaError, setNasaError] = useState(null)
  const [nasaLoading, setNasaLoading] = useState(false)
  const [appError, setAppError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

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
  }, [])

  useEffect(() => {
    loadDemo()
      .catch((error) => setAppError(error.message))
      .finally(() => setLoading(false))
  }, [loadDemo])

  useEffect(() => {
    const prefersReducedMotion = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (loading || prefersReducedMotion) return undefined

    const revealTargets = document.querySelectorAll('[data-reveal]')
    if (!revealTargets.length || typeof window.IntersectionObserver !== 'function') return undefined

    document.documentElement.classList.add('reveal-ready')
    const observer = new window.IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.01, rootMargin: '0px 0px -32px 0px' })

    revealTargets.forEach((target) => observer.observe(target))
    return () => {
      observer.disconnect()
      document.documentElement.classList.remove('reveal-ready')
    }
  }, [loading, currentPage])

  useEffect(() => {
    if (loading) return undefined
    const targetId = location.hash.slice(1)
    const frame = window.requestAnimationFrame(() => {
      if (targetId) {
        document.getElementById(decodeURIComponent(targetId))
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    })
    return () => window.cancelAnimationFrame(frame)
  }, [location.pathname, location.hash, loading])

  useEffect(() => {
    if (!mobileMenuOpen) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setMobileMenuOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [mobileMenuOpen])

  const handleMapCoordinateSelect = useCallback(async ({ lat, lon, regionCode, needsRefinement }) => {
    const requestId = ++mapSelectionRequest.current
    setDraftField((current) => ({
      ...current,
      lat: String(lat),
      lon: String(lon),
      region_code: regionCode || '',
    }))
    setFieldError(null)
    setPlaceName('')
    setPlaceNameStatus('checking')
    if (lat < 20 || lat > 37 || lon < -18 || lon > 0) {
      setPlaceNameStatus('not-found')
    } else {
      api(`/api/places/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`)
        .then((place) => {
          if (requestId !== mapSelectionRequest.current) return
          const label = [place.place_name, place.context]
            .filter((name, index, names) => name && names.indexOf(name) === index)
            .join(', ')
          setPlaceName(label)
          setPlaceNameStatus(label ? 'found' : 'not-found')
        })
        .catch(() => {
          if (requestId === mapSelectionRequest.current) {
            setPlaceNameStatus('unavailable')
          }
        })
    }

    if (regionCode) {
      const regionName = regions.find((region) => region.code === regionCode)?.name
      setMapLocationStatus('matched')
      const refinementNote = needsRefinement
        ? ' The map zoomed in; click again to refine the point.'
        : ''
      setMapLocationMessage(
        `${regionName ? `Selected ${regionName} from the map.` : 'Region selected from the map.'}${refinementNote}`
      )
      return
    }

    setMapLocationStatus('checking')
    setMapLocationMessage('Detecting the administrative region...')
    try {
      const location = await api(
        `/api/regions/locate?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`
      )
      if (requestId !== mapSelectionRequest.current) return
      if (location.region_codes.length === 1) {
        const code = location.region_codes[0]
        const regionName = location.regions[0]?.name || 'the mapped region'
        setDraftField((current) => ({ ...current, region_code: code }))
        setMapLocationStatus('matched')
        setMapLocationMessage(`Detected ${regionName}.`)
      } else if (location.region_codes.length > 1) {
        const matchingNames = location.regions.map((region) => region.name).join(' / ')
        setMapLocationStatus('ambiguous')
        setMapLocationMessage(`This point is on a shared boundary. Choose one of: ${matchingNames}.`)
      } else {
        setMapLocationStatus('outside')
        setMapLocationMessage('No administrative region was found for this point. Click within a mapped region.')
      }
    } catch {
      if (requestId !== mapSelectionRequest.current) return
      setMapLocationStatus('outside')
      setMapLocationMessage('This point is outside the mapped regions. Click within Morocco or enter the location manually.')
    }
  }, [regions])

  const lookupManualCoordinates = useCallback(() => {
    const lat = Number(draftField.lat)
    const lon = Number(draftField.lon)
    if (draftField.lat === '' || draftField.lon === '' ||
        !Number.isFinite(lat) || lat < 20 || lat > 37 ||
        !Number.isFinite(lon) || lon < -18 || lon > 0) return
    void handleMapCoordinateSelect({ lat, lon })
  }, [draftField.lat, draftField.lon, handleMapCoordinateSelect])

  const updateManualLocation = (key, value) => {
    mapSelectionRequest.current += 1
    setMapLocationStatus('idle')
    setMapLocationMessage('')
    if (key === 'lat' || key === 'lon') {
      setPlaceName('')
      setPlaceNameStatus('idle')
    }
    setFieldError(null)
    setDraftField((current) => ({
      ...current,
      [key]: value,
      ...(key === 'lat' || key === 'lon' ? { region_code: '' } : {}),
    }))
  }

  async function useSelectedField(event) {
    event.preventDefault()
    const lat = Number(draftField.lat)
    const lon = Number(draftField.lon)
    const areaHa = Number(draftField.area_ha)
    let region = regions.find((item) => item.code === draftField.region_code)
    if (!Number.isFinite(lat) || lat < 20 || lat > 37 ||
        !Number.isFinite(lon) || lon < -18 || lon > 0) {
      setFieldError('Enter coordinates within Morocco.')
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
    if (!region && location.region_codes.length === 1) {
      region = location.regions.find((item) => item.code === location.region_codes[0])
      if (region) {
        setDraftField((current) => ({ ...current, region_code: region.code }))
        setMapLocationStatus('matched')
        setMapLocationMessage(`Detected ${region.name} from the entered coordinates.`)
      }
    }
    if (!region) {
      const matchingNames = location.regions.map((item) => item.name).join(' / ')
      setFieldError(location.region_codes.length > 1
        ? `These coordinates are on a shared boundary. Choose one of: ${matchingNames}.`
        : 'No administrative region was found for these coordinates.')
      return
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
    setComparisonError(null)
    setSimulationInput(null)
  }

  function runSimulation() {
    if (!field) return
    const currentRotation = includeCurrentRotation &&
      crops.length === 3 && crops.every(Boolean)
      ? [...crops]
      : null
    setComparison(null)
    setComparisonError(null)
    setSimulationInput({
      current_rotation: currentRotation,
      scenario_id: activeScenario,
      priorities: { ...priorities },
      field: {
        region_code: field.region_code,
        lat: field.lat,
        lon: field.lon,
        area_ha: field.area_ha,
        irrigation: field.irrigation,
        soil: field.soil,
      },
    })
    navigate('/results')
  }

  function updateAssessmentField(key, value) {
    setFarmAssessment((current) => ({ ...current, [key]: value }))
  }

  function updateAssessmentCrop(index, key, value) {
    setFarmAssessment((current) => ({
      ...current,
      crops: current.crops.map((crop, cropIndex) => (
        cropIndex === index ? { ...crop, [key]: value } : crop
      )),
    }))
  }

  function toggleObservedIssue(issue) {
    setFarmAssessment((current) => ({
      ...current,
      observed_issues: current.observed_issues.includes(issue)
        ? current.observed_issues.filter((item) => item !== issue)
        : [...current.observed_issues, issue],
    }))
  }

  function restoreFarmProfile(profile) {
    const savedField = profile.field
    const soil = savedField.soil && typeof savedField.soil === 'object'
      ? savedField.soil
      : {}
    const locationChanged = !field ||
      Number(field.lat) !== Number(savedField.lat) ||
      Number(field.lon) !== Number(savedField.lon)
    if (locationChanged) skipAssessmentResetRef.current = true

    const matchedRegion = regions.find((region) => region.code === savedField.region_code)
    const restoredField = {
      ...savedField,
      region_name: savedField.region_name || matchedRegion?.name || 'Region not identified',
    }
    setField(restoredField)
    setDraftField({
      ...DEFAULT_FIELD_DRAFT,
      region_code: restoredField.region_code || '',
      lat: String(restoredField.lat),
      lon: String(restoredField.lon),
      area_ha: String(restoredField.area_ha),
      irrigation: restoredField.irrigation || 'unknown',
      soil_type: soil.soil_type || '',
      sand_pct: soil.sand_pct === undefined ? '' : String(soil.sand_pct),
      silt_pct: soil.silt_pct === undefined ? '' : String(soil.silt_pct),
      clay_pct: soil.clay_pct === undefined ? '' : String(soil.clay_pct),
      ph: soil.ph === undefined ? '' : String(soil.ph),
      organic_c_pct: soil.organic_c_pct === undefined ? '' : String(soil.organic_c_pct),
      nacl_ppth: soil.nacl_ppth === undefined ? '' : String(soil.nacl_ppth),
    })
    setFarmAssessment(normalizeFarmAssessment(profile.baseline))
    setPlaceName('')
    setPlaceNameStatus('idle')
    setFieldError(null)
    setComparison(null)
    setComparisonError(null)
    setSimulationInput(null)
  }

  function restoreSimulationRun(run) {
    restoreFarmProfile({ field: run.field, baseline: farmAssessment })
    const restoredPriorities = {
      water: run.inputs.priorities.water,
      nitrogen: run.inputs.priorities.nitrogen,
      resilience: run.inputs.priorities.resilience,
      soil: run.inputs.priorities.soil,
      economy: run.inputs.priorities.economy,
    }
    const restoredInput = {
      current_rotation: run.inputs.current_rotation,
      scenario_id: run.inputs.scenario_id,
      priorities: restoredPriorities,
      field: {
        region_code: run.field.region_code,
        lat: Number(run.field.lat),
        lon: Number(run.field.lon),
        area_ha: Number(run.field.area_ha),
        irrigation: run.field.irrigation,
        soil: run.field.soil ?? null,
      },
    }
    setActiveScenario(restoredInput.scenario_id)
    setPriorities(restoredPriorities)
    const currentRotation = run.inputs.current_rotation
    setIncludeCurrentRotation(Array.isArray(currentRotation) && currentRotation.length === 3)
    setCrops(Array.isArray(currentRotation) && currentRotation.length === 3
      ? currentRotation
      : ['', '', ''])
    skipNextSimulationRef.current = true
    setSimulationInput(restoredInput)
    setComparison(run.result)
    setComparisonError(null)
    navigate('/results')
  }

  function clearFarmProfileFromPage() {
    setField(null)
    setDraftField(DEFAULT_FIELD_DRAFT)
    setFarmAssessment(createFarmAssessment())
    setCrops(['', '', ''])
    setIncludeCurrentRotation(false)
    setPlaceName('')
    setPlaceNameStatus('idle')
    setFieldError(null)
    setComparison(null)
    setComparisonError(null)
    setSimulationInput(null)
  }

  useEffect(() => {
    if (!field) {
      setNasaData(null)
      setNasaError(null)
      setNasaLoading(false)
      return
    }
    let cancelled = false
    async function run() {
      setNasaLoading(true)
      setNasaError(null)
      try {
        const data = await api(
          `/api/nasa?lat=${encodeURIComponent(field.lat)}&lon=${encodeURIComponent(field.lon)}`
        )
        if (!cancelled) setNasaData(data)
      } catch (error) {
        if (!cancelled) {
          setNasaData(null)
          setNasaError(error.message)
        }
      } finally {
        if (!cancelled) setNasaLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [field?.lat, field?.lon])

  useEffect(() => {
    if (!simulationInput) {
      setComparing(false)
      return undefined
    }
    if (skipNextSimulationRef.current) {
      skipNextSimulationRef.current = false
      setComparing(false)
      return undefined
    }

    let cancelled = false
    async function run() {
      setComparing(true)
      setComparisonError(null)
      try {
        const comp = await api('/api/recommendations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(simulationInput),
        })
        if (!cancelled) setComparison(comp)
      } catch (error) {
        if (!cancelled) {
          setComparison(null)
          setComparisonError(error.message)
        }
      } finally {
        if (!cancelled) setComparing(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [simulationInput])

  useEffect(() => {
    if (skipAssessmentResetRef.current) {
      skipAssessmentResetRef.current = false
      return
    }
    setFarmAssessment(createFarmAssessment())
  }, [field?.lat, field?.lon])

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
    const resultScenarioId = simulationInput?.scenario_id || activeScenario
    const resultScenario = scenarios.find((scenario) => scenario.id === resultScenarioId) || sc
    const comparisonA = comparison
    const activeRows = comparisonA
      ? comparisonA.comparison.filter(c => c.scenario_id === resultScenarioId)
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
    const selectedRegion = regions.find((region) => region.code === draftField.region_code)
    const selectedCurrentRotation = includeCurrentRotation &&
      crops.length === 3 && crops.every(Boolean)
      ? crops
      : null
    const currentSimulationInput = field ? {
      current_rotation: selectedCurrentRotation,
      scenario_id: activeScenario,
      priorities,
      field: {
        region_code: field.region_code,
        lat: field.lat,
        lon: field.lon,
        area_ha: field.area_ha,
        irrigation: field.irrigation,
        soil: field.soil,
      },
    } : null
    const simulationInputsChanged = Boolean(
      simulationInput && currentSimulationInput &&
      JSON.stringify(simulationInput) !== JSON.stringify(currentSimulationInput)
    )
    const selectedPlaceLabel = placeName || (
      placeNameStatus === 'checking'
        ? 'Looking up the nearby locality…'
        : placeNameStatus === 'unavailable'
          ? 'Locality lookup is temporarily unavailable'
          : placeNameStatus === 'not-found'
            ? 'No named locality is available for this point'
            : 'Enter coordinates to identify a nearby locality'
    )
    const selectedRegionLabel = selectedRegion?.name || (
      mapLocationStatus === 'checking'
        ? 'Identifying the administrative region…'
        : mapLocationStatus === 'ambiguous'
          ? 'Point on an administrative boundary'
          : mapLocationStatus === 'outside'
            ? 'No named administrative region found'
            : 'Not detected yet'
    )
    const hasDraftCoordinates = draftField.lat !== '' && draftField.lon !== '' &&
      Number.isFinite(Number(draftField.lat)) && Number.isFinite(Number(draftField.lon))

  return (
    <div className="app">
      <nav className="site-nav" aria-label="Main navigation">
        <BrandLockup onClick={() => setMobileMenuOpen(false)} />
        <div className={`site-nav-links${mobileMenuOpen ? ' is-open' : ''}`} id="primary-navigation">
          {PAGE_FLOW.map(({ key, path, label }) => (
            <Link
              key={key}
              to={path}
              aria-current={currentPage === key ? 'page' : undefined}
              onClick={() => setMobileMenuOpen(false)}
            >
              {label}
            </Link>
          ))}
        </div>
        <Link className="nav-action" to="/data" onClick={() => setMobileMenuOpen(false)}>Begin <span aria-hidden="true">↗</span></Link>
        <button
          className="mobile-menu-toggle"
          type="button"
          aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={mobileMenuOpen}
          aria-controls="primary-navigation"
          onClick={() => setMobileMenuOpen((open) => !open)}
        >
          <span className={`menu-toggle-lines${mobileMenuOpen ? ' is-open' : ''}`} aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </button>
      </nav>

      {currentPage === 'home' && (
        <>
      <header className="header" id="top">
        <img
          className="hero-artwork"
          src="/nex-terra-hero.jpg"
          alt="NEX TERRA — Adapting farms with NASA data. Smart rotation, resilient agriculture and a sustainable future. Satellite data, crop rotation, water optimization and climate resilience above an agricultural field."
          loading="eager"
          decoding="async"
        />
        <div className="hero-copy">
          <h1>A resilient future starts on <em>your land.</em></h1>
        </div>
      </header>
        </>
      )}

      <main>
        {currentPage === 'home' && (
          <>
        <section className="hero-details" aria-label="Explore NEX TERRA" data-reveal>
          <div className="hero-detail-copy">
            <p>Explore how different crop rotations could respond to your farm, your priorities and a changing climate.</p>
            <span className="tagline">Morocco <span aria-hidden="true">·</span> 12 administrative regions</span>
          </div>
          <div className="hero-actions">
            <Link className="primary-button hero-button" to="/data">Start simulation <span aria-hidden="true">↗</span></Link>
            <Link className="text-button hero-text-button" to="/about">Explore the project</Link>
          </div>
        </section>
            <PageStepNavigation currentPage={currentPage} />
          </>
        )}

        {currentPage === 'about' && (
          <>
        <div className="intro-band" id="approach" data-reveal>
          <p className="eyebrow">A decision-support tool</p>
          <p>Grounded in satellite observations. Designed to make trade-offs visible. Built to support the farmer’s judgment—not replace it.</p>
          <Link to="/data#catalog">Understand the evidence <span aria-hidden="true">↗</span></Link>
        </div>

        <section className="journey-section about-section" id="about" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">02 / About NEX TERRA</span>
            <h2>Make climate and crop choices easier to explore.</h2>
            <p>NEX TERRA is an exploratory decision-support prototype for Moroccan agriculture. It brings field context, sourced crop evidence and rotation scenarios into one place—without presenting its estimates as farm advice.</p>
          </div>
          <div className="about-grid">
            <article>
              <span>01</span>
              <h3>The challenge</h3>
              <p>Farmers must navigate changing rainfall and temperatures, water constraints and soil-health pressures while making decisions with incomplete local data.</p>
            </article>
            <article>
              <span>02</span>
              <h3>The approach</h3>
              <p>Explore supported crop sequences against gridded climate context, optional farmer-entered soil information and the priorities that matter to each user.</p>
            </article>
            <article>
              <span>03</span>
              <h3>What is innovative</h3>
              <p>Compare trade-offs and evidence gaps together, so users can question the assumptions instead of receiving an unexplained “best crop” answer.</p>
            </article>
          </div>
        </section>

        <ol className="journey-steps" aria-label="How NEX TERRA works" data-reveal>
          <li><span>01</span><strong>Understand the context</strong></li>
          <li><span>02</span><strong>Configure a scenario</strong></li>
          <li><span>03</span><strong>Run the simulation</strong></li>
          <li><span>04</span><strong>Review the trade-offs</strong></li>
        </ol>
            <PageStepNavigation currentPage={currentPage} />
          </>
        )}

        {currentPage === 'data' && (
          <>
        <section className="journey-section data-section" id="data" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">03 / Agricultural data & context</span>
            <h2>Start with a place, then review the evidence.</h2>
            <p>Set the field point and farm details first. Climate estimates, soil inputs and crop evidence are shown with their provenance and known gaps.</p>
          </div>
        <div className="layout" id="workspace">
          <div className="workspace-column" data-reveal>
            <div className="section-lead" id="location">
              <span className="eyebrow">01 / Your place</span>
              <h2>Start with the land you know.</h2>
              <p>Select a point on the map or enter coordinates manually. NEX TERRA will identify the nearest named place and check its administrative region where data is available.</p>
            </div>
          <section className="card location-panel">
            <div className="location-heading">
              <span className="step-number">01</span>
              <div>
                <h2>Choose your exact farm location</h2>
                <p className="sub">Choose a map point or enter coordinates below to identify a nearby place and region.</p>
              </div>
            </div>
            <FieldMap
              draftField={draftField}
              regionBoundaries={regionBoundaries}
              regions={regions}
              onCoordinateSelect={handleMapCoordinateSelect}
            />
            <div className={`location-readout location-${mapLocationStatus}`} aria-live="polite">
              {hasDraftCoordinates ? (
                <>
                  <strong>Selected place</strong>
                  <span>{selectedPlaceLabel}</span>
                  <strong>Administrative region</strong>
                  <span>{selectedRegionLabel}</span>
                  <strong>Coordinates</strong>
                  <span>{Number(draftField.lat).toFixed(5)}, {Number(draftField.lon).toFixed(5)}</span>
                </>
              ) : (
                <span>Choose a point on the map to begin.</span>
              )}
              {mapLocationMessage && <p role={mapLocationStatus === 'outside' ? 'alert' : 'status'}>{mapLocationMessage}</p>}
            </div>
            <p className="map-attribution">
              Nearby place names are looked up with <a href="https://nominatim.openstreetmap.org/" target="_blank" rel="noreferrer">OpenStreetMap Nominatim</a>; selecting a point sends its coordinates to that service. Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>.
            </p>
          </section>

          <form className="card field-selector" onSubmit={useSelectedField}>
            <div className="location-heading">
              <span className="step-number">02</span>
              <div>
                <h2>Confirm farm details</h2>
                <p className="sub">Review the location and enter the farm information. Coordinates entered manually are used to detect the region automatically when possible.</p>
              </div>
            </div>
            <label>
              Administrative region
              <select
                value={draftField.region_code}
                onChange={(event) => updateManualLocation('region_code', event.target.value)}
              >
                <option value="">Auto-detect from coordinates, or select a region</option>
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
                  onChange={(event) => updateManualLocation('lat', event.target.value)}
                  onBlur={lookupManualCoordinates}
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
                  onChange={(event) => updateManualLocation('lon', event.target.value)}
                  onBlur={lookupManualCoordinates}
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

          <FarmAccountPanel
            field={field}
            baseline={farmAssessment}
            onProfileLoaded={restoreFarmProfile}
            onSignedOut={clearFarmProfileFromPage}
          />

          {field && (
            <div className="card selected-farm-card">
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

          {field && (
            <section className="farm-assessment" aria-labelledby="farm-assessment-title">
              <div className="section-lead compact">
                <span className="eyebrow">Current farm baseline</span>
                <h2 id="farm-assessment-title">Record what is happening on this land.</h2>
                <p>Enter what you know about current crops, water, soil, inputs and visible conditions. Leave unknown items blank.</p>
              </div>
              <p className="assessment-disclosure">
                These are farmer-reported records, not an automatic diagnosis. They remain in this browser session unless you explicitly save them to your signed-in account. They do not affect scores; soil measurements entered above are sent with a simulation and used by its existing unvalidated prototype model.
              </p>

              <div className="assessment-group">
                <h3>Current crops and rotation</h3>
                <p className="sub">Add up to three recent or current crops. Crop names can be entered freely, including crops not supported by the simulator.</p>
                <div className="farm-crop-records">
                  {farmAssessment.crops.map((crop, index) => (
                    <fieldset className="farm-crop-record" key={index}>
                      <legend>Crop {index + 1}</legend>
                      <label>
                        Crop name
                        <input
                          type="text"
                          maxLength="80"
                          placeholder="e.g. durum wheat, olive, vegetables"
                          value={crop.name}
                          onChange={(event) => updateAssessmentCrop(index, 'name', event.target.value)}
                        />
                      </label>
                      <div className="assessment-field-grid">
                        <label>
                          Sowing date
                          <input
                            type="date"
                            value={crop.sowing_date}
                            onChange={(event) => updateAssessmentCrop(index, 'sowing_date', event.target.value)}
                          />
                        </label>
                        <label>
                          Harvest date
                          <input
                            type="date"
                            value={crop.harvest_date}
                            onChange={(event) => updateAssessmentCrop(index, 'harvest_date', event.target.value)}
                          />
                        </label>
                        <label>
                          Known yield (t/ha)
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={crop.yield_t_ha}
                            onChange={(event) => updateAssessmentCrop(index, 'yield_t_ha', event.target.value)}
                          />
                        </label>
                        <label>
                          Yield record
                          <select
                            value={crop.yield_source}
                            onChange={(event) => updateAssessmentCrop(index, 'yield_source', event.target.value)}
                          >
                            <option value="unknown">Unknown</option>
                            <option value="measured">Measured / recorded</option>
                            <option value="estimated">Estimated by farmer</option>
                          </select>
                        </label>
                        <label>
                          Yield year
                          <input
                            type="number"
                            min="1900"
                            max="2100"
                            step="1"
                            value={crop.yield_year}
                            onChange={(event) => updateAssessmentCrop(index, 'yield_year', event.target.value)}
                          />
                        </label>
                      </div>
                    </fieldset>
                  ))}
                </div>
              </div>

              <div className="assessment-group">
                <h3>Water and irrigation</h3>
                <div className="assessment-field-grid">
                  <label>
                    Main water source
                    <select
                      value={farmAssessment.irrigation_source}
                      onChange={(event) => updateAssessmentField('irrigation_source', event.target.value)}
                    >
                      <option value="unknown">Unknown / not supplied</option>
                      <option value="rainfed">Rainfall only</option>
                      <option value="surface_water">Surface water / canal</option>
                      <option value="groundwater">Groundwater / well</option>
                      <option value="reused_water">Reused water</option>
                      <option value="mixed">Several sources</option>
                      <option value="other">Other</option>
                    </select>
                  </label>
                  <label>
                    Irrigation method
                    <select
                      value={farmAssessment.irrigation_method}
                      onChange={(event) => updateAssessmentField('irrigation_method', event.target.value)}
                    >
                      <option value="unknown">Unknown / not supplied</option>
                      <option value="surface">Surface / furrow</option>
                      <option value="drip">Drip</option>
                      <option value="sprinkler">Sprinkler</option>
                      <option value="other">Other</option>
                    </select>
                  </label>
                  <label>
                    Water availability
                    <select
                      value={farmAssessment.water_availability}
                      onChange={(event) => updateAssessmentField('water_availability', event.target.value)}
                    >
                      <option value="unknown">Unknown / not supplied</option>
                      <option value="reliable">Usually reliable</option>
                      <option value="seasonal">Seasonal variation</option>
                      <option value="limited">Often limited</option>
                      <option value="other">Other / varies</option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="assessment-group">
                <h3>Soil analysis and its source</h3>
                <p className="sub">Enter values under “Optional local soil measurements” above, then identify where they came from.</p>
                <div className="assessment-field-grid">
                  <label>
                    Soil information source
                    <select
                      value={farmAssessment.soil_source}
                      onChange={(event) => updateAssessmentField('soil_source', event.target.value)}
                    >
                      <option value="unknown">Unknown / not supplied</option>
                      <option value="laboratory">Laboratory analysis</option>
                      <option value="field_test">Field test / kit</option>
                      <option value="farmer_estimate">Farmer estimate</option>
                    </select>
                  </label>
                  <label>
                    Soil sample date
                    <input
                      type="date"
                      value={farmAssessment.soil_sample_date}
                      onChange={(event) => updateAssessmentField('soil_sample_date', event.target.value)}
                    />
                  </label>
                </div>
                <Link className="assessment-form-link" to="/data#location">Go to the soil measurement fields <span aria-hidden="true">↗</span></Link>
              </div>

              <div className="assessment-group">
                <h3>Fertilization and organic inputs</h3>
                <div className="assessment-field-grid">
                  <label>
                    Fertilizer or amendment name
                    <input
                      type="text"
                      maxLength="120"
                      value={farmAssessment.fertilizer_name}
                      onChange={(event) => updateAssessmentField('fertilizer_name', event.target.value)}
                    />
                  </label>
                  <label>
                    Rate and unit as recorded
                    <input
                      type="text"
                      maxLength="80"
                      placeholder="e.g. 50 kg/ha"
                      value={farmAssessment.fertilizer_rate}
                      onChange={(event) => updateAssessmentField('fertilizer_rate', event.target.value)}
                    />
                  </label>
                  <label className="assessment-wide-field">
                    Other organic inputs or notes
                    <input
                      type="text"
                      maxLength="160"
                      placeholder="e.g. manure or compost, if known"
                      value={farmAssessment.organic_inputs}
                      onChange={(event) => updateAssessmentField('organic_inputs', event.target.value)}
                    />
                  </label>
                </div>
              </div>

              <div className="assessment-group">
                <h3>Visible conditions and problems</h3>
                <p className="sub">Select observations only; these choices are not a diagnosis of the cause.</p>
                <div className="observed-issues">
                  {OBSERVED_FIELD_ISSUES.map((issue) => (
                    <label key={issue}>
                      <input
                        type="checkbox"
                        checked={farmAssessment.observed_issues.includes(issue)}
                        onChange={() => toggleObservedIssue(issue)}
                      />
                      <span>{issue}</span>
                    </label>
                  ))}
                </div>
                <label className="assessment-notes">
                  Other observations
                  <textarea
                    rows="3"
                    maxLength="500"
                    value={farmAssessment.observation_notes}
                    onChange={(event) => updateAssessmentField('observation_notes', event.target.value)}
                  />
                </label>
              </div>

              <div className="farm-assessment-summary" aria-live="polite">
                <span className="eyebrow">Your current baseline</span>
                <p><strong>Current crops:</strong> {farmAssessment.crops
                  .filter((crop) => crop.name.trim())
                  .map((crop) => `${crop.name}${crop.yield_t_ha ? ` — ${crop.yield_t_ha} t/ha` : ''}`)
                  .join(' · ') || 'Not entered yet'}</p>
                <p><strong>Water availability:</strong> {farmAssessment.water_availability === 'unknown'
                  ? 'Not entered'
                  : farmAssessment.water_availability.replaceAll('_', ' ')}</p>
                <p><strong>Observed conditions:</strong> {farmAssessment.observed_issues.length
                  ? farmAssessment.observed_issues.join(', ')
                  : 'No observations entered'}</p>
              </div>
            </section>
          )}
        </div>
        </div>

        <section className="climate-context-section" aria-labelledby="climate-context-title">
          <div className="section-lead compact">
            <span className="eyebrow">Field climate context</span>
            <h2 id="climate-context-title">Weather evidence for the selected point.</h2>
          </div>
          {!field && (
            <div className="data-empty-state">
              <p>Select and confirm a field to request its NASA POWER climate context and view the monthly chart.</p>
            </div>
          )}
          {nasaLoading && <p className="loading-status" role="status">Loading climate context for the selected coordinates…</p>}
          {nasaError && <p className="error-message" role="alert">Climate data could not be loaded: {nasaError}</p>}
          {nasaData && (
            <>
              <div className="nasa-summary">
                <div className="sub" style={{ fontWeight: 700, marginBottom: 6 }}>
                  {nasaData.data_status === 'partial'
                    ? 'NASA POWER daily estimates + synthetic placeholders'
                    : 'Synthetic demo values — NASA POWER unavailable'}
                </div>
                <div className="sub"><b>Mean air temperature:</b> {nasaData.temp_mean_c.toFixed(2)} °C ({sourceLabel(nasaData.source_status?.temp_mean_c)}) · <b>Precipitation total:</b> {nasaData.rainfall_mm_tot.toFixed(1)} mm ({sourceLabel(nasaData.source_status?.rainfall_mm_tot)})</div>
                <div className="sub"><b>Relative humidity:</b> {nasaData.humidity_pct.toFixed(0)}% ({sourceLabel(nasaData.source_status?.humidity_pct)}) · <b>Solar radiation:</b> {Number.isFinite(nasaData.solar_radiation_mj_m2_day) ? `${nasaData.solar_radiation_mj_m2_day.toFixed(1)} MJ/m²/day` : 'unavailable'} ({sourceLabel(nasaData.source_status?.solar_radiation_mj_m2_day)}) · <b>Wind:</b> {Number.isFinite(nasaData.wind_mean_ms) ? `${nasaData.wind_mean_ms.toFixed(1)} m/s` : 'unavailable'} ({sourceLabel(nasaData.source_status?.wind_mean_ms)})</div>
                <div className="sub"><b>Reference ET0:</b> {Number.isFinite(nasaData.et0_mean_mm_day) ? `${nasaData.et0_mean_mm_day.toFixed(2)} mm/day` : 'unavailable'} ({sourceLabel(nasaData.source_status?.et0)}) · {Number.isFinite(nasaData.elevation_m) ? `${nasaData.elevation_m.toFixed(0)} m site elevation` : 'site elevation unavailable'}</div>
                <div className="sub"><b>Vegetation (EVI):</b> {nasaData.evi.toFixed(3)} ({sourceLabel(nasaData.source_status?.evi)}) · <b>Soil moisture:</b> {nasaData.sm.toFixed(3)} ({sourceLabel(nasaData.source_status?.sm)}) · <b>Future climate:</b> {sourceLabel(nasaData.source_status?.cmip6)}</div>
                <div className="sub">{Number.isFinite(nasaData.lat) ? nasaData.lat.toFixed(3) : '—'}, {Number.isFinite(nasaData.lon) ? nasaData.lon.toFixed(3) : '—'} · {nasaData.observed_window_years?.join('–') || 'period unavailable'} · Values are gridded estimates, not field-sensor measurements.</div>
                <div className="sub nasa-source-note">{nasaData.source_note || 'Data provenance is not supplied.'}</div>
              </div>
              {nasaData.data_status === 'partial' && <PowerMonthlyChart nasaData={nasaData} />}
            </>
          )}
        </section>

        <section className="card crop-catalog" id="catalog" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">Crop evidence library</span>
            <h2>Morocco’s crop landscape.</h2>
          </div>
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
        </section>
            <PageStepNavigation currentPage={currentPage} />
          </>
        )}

        {currentPage === 'simulation' && (
          <>
        <section className="journey-section simulation-section" id="simulation" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">04 / Simulation setup</span>
            <h2>Choose how to explore your field.</h2>
            <p>Review the climate scenario, optional current rotation and priorities before asking the prototype to generate candidate sequences.</p>
          </div>
          {!field ? (
            <div className="card empty-state">
              <h2>Choose a field before configuring the simulation.</h2>
              <p className="sub">Set a point in the Agricultural Data section to enable the configuration and run controls.</p>
              <Link className="primary-button" to="/data">Choose your field <span aria-hidden="true">↗</span></Link>
            </div>
          ) : (
          <div className="card analysis-controls">
            <h2>Explore rotation options for your farm</h2>
            <p className="sub">NEX TERRA generates three exploratory rotations from its supported annual-crop models using your selected scenario, soil inputs, and priorities. These are prototype options, not validated local recommendations.</p>

            <div className="scenario-panel">
            <label className="slider-label">Climate stress-test scenario</label>
              <input
                type="range"
                min={0}
                max={scenarios.length - 1}
                value={scenarios.findIndex(s => s.id === activeScenario)}
                onChange={e => setActiveScenario(scenarios[e.target.value].id)}
                className="scenario-slider"
              />
              <label className="current-rotation-toggle">
                <input
                  type="checkbox"
                  checked={includeCurrentRotation}
                  onChange={event => {
                    setIncludeCurrentRotation(event.target.checked)
                    if (event.target.checked) setCrops(['', '', ''])
                  }}
                />
                Compare a simulator-supported three-crop baseline
              </label>
              {includeCurrentRotation && (
                <div className="rotation-inputs">
                  <strong>Optional model baseline (one supported annual crop per position)</strong>
                  <span className="sub">This comparison is separate from the full current-farm record above. Only simulator-supported annual crops can be compared; unknown or perennial crops can still be recorded in the farm profile.</span>
                  {crops.map((crop, index) => (
                    <label key={index}>
                      Sequence position {index + 1}
                      <select
                        value={crop}
                        onChange={event => setCrops(current =>
                          current.map((item, cropIndex) =>
                            cropIndex === index ? event.target.value : item
                          )
                        )}
                      >
                        <option value="">Choose an annual crop</option>
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
              )}
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
              <div className="sub">These sliders are your preferences, not NASA measurements. Move a priority higher when it matters more; the model normalizes the relative weights before scoring. Scenario shifts and crop coefficients are illustrative, not regionally validated.</div>
              <div className="future-banner">
                <p><strong>{activeScenario.replace(/_/g, ' ')}</strong></p>
                <p>+{sc.temp_shift.toFixed(1)}°C warming · precipitation {sc.precipitation >= 1 ? '+' : ''}{Math.round((sc.precipitation - 1) * 100)}% · drought index {sc.drought.toFixed(2)}</p>
            </div>
            </div>

            <section className="simulation-launch" id="simulation-run" aria-labelledby="simulation-review-title">
              <span className="eyebrow">05 / Run the simulation</span>
              <h3 id="simulation-review-title">Review your setup</h3>
              <div className="simulation-review">
                <div><span>Field</span><strong>{field.region_name} · {field.lat.toFixed(3)}, {field.lon.toFixed(3)}</strong></div>
                <div><span>Scenario</span><strong>{sc.label}</strong></div>
                <div><span>Soil inputs</span><strong>{field.soil ? 'Farmer-provided values included' : 'Not supplied · prototype defaults'}</strong></div>
                <div><span>Current rotation</span><strong>{selectedCurrentRotation ? selectedCurrentRotation.map(code => cropCatalog.crops.find(crop => crop.code === code)?.name || code).join(' · ') : includeCurrentRotation ? 'Incomplete; it will not be compared' : 'Not included'}</strong></div>
                <div className="simulation-review-priorities">
                  <span>Priority weights</span>
                  <strong>{Object.entries(priorities).map(([key, value]) => `${PRIORITY_LABELS[key]} ${Math.round(value * 100)}%`).join(' · ')}</strong>
                </div>
              </div>
              <p className="sub">The run searches supported three-crop sequences and scores them with prototype assumptions. It does not create region-specific planting calendars or validated farm advice.</p>
              <button
                type="button"
                className="primary-button simulation-run-button"
                onClick={runSimulation}
                disabled={comparing || fieldValidationLoading}
              >
                {comparing ? 'Generating options…' : comparison ? 'Run again with this setup' : 'Start simulation'}
                {!comparing && <span aria-hidden="true"> ↗</span>}
              </button>
              {comparing && (
                <p className="loading-status simulation-progress" role="status">
                  <span className="loading-spinner" aria-hidden="true" />
                  Generating candidate rotations and calculating comparison metrics…
                </p>
              )}
              {simulationInput && !comparing && !comparisonError && comparison && (
                <p className="simulation-success" role="status">Results are ready below for the reviewed setup.</p>
              )}
            </section>
          </div>
          )}
        </section>
          <SimulationHistoryPanel
            field={field}
            simulationInput={simulationInput}
            result={comparison}
            onRunLoaded={restoreSimulationRun}
          />
            <PageStepNavigation currentPage={currentPage} />
          </>
        )}

        {currentPage === 'results' && (
          <>
        <section className="journey-section results-section" id="results" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">06 / Results & analytics</span>
            <h2>Compare the trade-offs, not just a single score.</h2>
            <p>Review modelled water demand, crop sequence, resilience, soil protection and the assumptions behind each option.</p>
          </div>
          {!comparison && !comparing && !comparisonError && (
            <div className="card empty-state">
              <h3>Your results will appear here after the simulation.</h3>
              <p className="sub">The selected field, climate context and crop catalogue are available above. Review the simulation setup and launch it when ready.</p>
              <Link className="primary-button" to="/simulation">Review and launch <span aria-hidden="true">↗</span></Link>
            </div>
          )}
          {comparisonError && <p className="error-message" role="alert">Simulation could not be completed: {comparisonError}</p>}
          {simulationInputsChanged && comparison && (
            <p className="stale-results-notice" role="status">
              Your setup has changed since this run. The results below still represent the last launched setup; run again to refresh them.
            </p>
          )}
          {comparing && (
            <p className="loading-status" role="status">
              <span className="loading-spinner" aria-hidden="true" />
              The simulation is running. Results will appear here when the calculation finishes.
            </p>
          )}
            {comparisonA && (
              <>
                <section className="comparison-context" aria-label="How to interpret this comparison">
                  <h3>Prototype comparison — not a crop recommendation</h3>
                  <p><strong>Scenario used for these results:</strong> {resultScenario.label}</p>
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
                  Cross-scenario rank is based on mean prototype score across all scenarios; the table shows metrics for the scenario used in the last run.
                </div>
                <ComparisonCharts rows={activeRows} />
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
        </section>
            <PageStepNavigation currentPage={currentPage} />
          </>
        )}

        {currentPage === 'methodology' && (
          <>
        <section className="journey-section methodology-section" id="methodology" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">07 / Methodology & limits</span>
            <h2>Make every assumption visible.</h2>
            <p>The prototype combines established climate references with illustrative crop and rotation assumptions. These evidence types are not interchangeable.</p>
          </div>
          <div className="methodology-grid">
            <article>
              <span className="methodology-index">01</span>
              <h3>Climate context</h3>
              <p>NASA POWER provides gridded estimates for the selected point, not field-sensor readings. Reference ET₀ follows the FAO-56 Penman–Monteith method when source coverage is sufficient.</p>
              <a href="https://power.larc.nasa.gov/" target="_blank" rel="noreferrer">NASA POWER <span aria-hidden="true">↗</span></a>
            </article>
            <article>
              <span className="methodology-index">02</span>
              <h3>Crop evidence</h3>
              <p>Crop presence and source coverage are shown separately. Unknown regional evidence stays unknown; administrative regions are not converted into invented crop calendars.</p>
              <Link to="/data#catalog">Review the crop catalogue <span aria-hidden="true">↗</span></Link>
            </article>
            <article>
              <span className="methodology-index">03</span>
              <h3>Rotation model</h3>
              <p>Candidate sequences and weighted scores use prototype coefficients and assumptions. Some indicators are synthetic; results have not been validated as agronomic recommendations.</p>
              <Link to="/results">Inspect the model outputs <span aria-hidden="true">↗</span></Link>
            </article>
          </div>
          <p className="methodology-caveat"><strong>Use with care.</strong> Results are for exploration and discussion. They are not planting calendars, irrigation schedules, yield forecasts, financial advice or a substitute for local agronomic expertise.</p>
        </section>
            <PageStepNavigation currentPage={currentPage} />
          </>
        )}

        {currentPage === 'team' && (
          <>
        <section className="journey-section team-section" id="team" data-reveal>
          <div className="section-lead">
            <span className="eyebrow">08 / Team & acknowledgements</span>
            <h2>A project profile, not an invented roster.</h2>
            <p>We share only team details that are available from a public source.</p>
          </div>
          <div className="team-profile">
            <div>
              <span className="team-profile-label">Public project profile</span>
              <h3>NEX TERRA · Field Shift</h3>
              <p>The public Space Apps profile lists NEX TERRA as a participating team associated with the Casablanca event and the Field Shift challenge.</p>
              <a href="https://www.spaceappschallenge.org/2026/find-a-team/nex-terra/" target="_blank" rel="noreferrer">View the NEX TERRA profile <span aria-hidden="true">↗</span></a>
            </div>
            <p className="team-disclosure">The profile is participant-submitted and is not evidence of NASA sponsorship, endorsement or a formal partnership. It does not publish verified individual names, roles or contact details, so none are inferred here.</p>
          </div>
            <PageStepNavigation currentPage={currentPage} />
        </section>
          </>
        )}
      </main>
      {currentPage === 'team' && (
        <footer className="site-footer" data-reveal>
        <div className="footer-brand-block">
          <BrandLockup className="footer-brand" />
          <p>Smarter rotations. A more resilient future.</p>
        </div>
        <section className="footer-sources" id="sources" aria-labelledby="sources-title">
          <div className="footer-sources-heading">
            <span className="eyebrow">Evidence & acknowledgements</span>
            <h2 id="sources-title">Explore the sources behind NEX TERRA.</h2>
            <p>Data and references used by this prototype. Crop links open the source records in the Moroccan crop catalogue.</p>
          </div>
          <div className="footer-source-groups">
            <section className="footer-source-group">
              <h3>Space agency & climate data</h3>
              <a href="https://power.larc.nasa.gov/" target="_blank" rel="noreferrer">NASA POWER <span>Gridded climate data</span></a>
              <a href="https://www.fao.org/4/x0490e/x0490e07.htm" target="_blank" rel="noreferrer">FAO-56 · Climate parameters <span>Chapter 3</span></a>
              <a href="https://www.fao.org/4/x0490e/x0490e08.htm" target="_blank" rel="noreferrer">FAO-56 · Reference ET₀ <span>Chapter 4 · Penman–Monteith method</span></a>
              <a href="https://www.spaceappschallenge.org/2026/find-a-team/nex-terra/" target="_blank" rel="noreferrer">NEX TERRA · NASA Space Apps Challenge <span>Team profile · competition participation, not NASA endorsement</span></a>
            </section>
            <section className="footer-source-group">
              <h3>Moroccan crop evidence</h3>
              {cropCatalog.sources.map((source) => (
                <a key={source.id} href={source.url} target="_blank" rel="noreferrer">
                  {source.title}<span>{source.publisher}</span>
                </a>
              ))}
            </section>
            <section className="footer-source-group">
              <h3>Maps & administrative regions</h3>
              {regionSource?.url && (
                <a href={regionSource.url} target="_blank" rel="noreferrer">
                  Moroccan local authorities <span>Administrative region reference</span>
                </a>
              )}
              {regionSource?.boundary_source?.url && (
                <a href={regionSource.boundary_source.url} target="_blank" rel="noreferrer">
                  geoBoundaries · Morocco ADM1 <span>Region boundary dataset · 2017</span>
                </a>
              )}
              {regionSource?.boundary_source?.license_url && (
                <a href={regionSource.boundary_source.license_url} target="_blank" rel="noreferrer">
                  Open Data Commons ODbL 1.0 <span>Boundary data license</span>
                </a>
              )}
              <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap <span>Map tiles and place-name attribution</span></a>
              <a href="https://github.com/manabouate-cell/NEX-TERRA" target="_blank" rel="noreferrer">NEX TERRA source code <span>Apache License 2.0</span></a>
            </section>
          </div>
        </section>
        <div className="footer-bottom">
          <nav className="footer-quick-links" aria-label="Footer navigation">
            {PAGE_FLOW.slice(1).map(({ key, path, label }) => (
              <Link key={key} to={path}>{label}</Link>
            ))}
          </nav>
          <small>© {new Date().getFullYear()} NEX TERRA · Exploratory prototype. NASA POWER values are gridded estimates, not field measurements. Rotation outputs are not validated agronomic advice; Space Apps participation does not imply NASA sponsorship or endorsement.</small>
        </div>
        </footer>
      )}
    </div>
  )
}
