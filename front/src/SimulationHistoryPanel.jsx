import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from './supabase'

function isValidSavedRun(run) {
  const field = run?.field
  const inputs = run?.inputs
  const result = run?.result
  const isRecord = (value) => Boolean(
    value && typeof value === 'object' && !Array.isArray(value)
  )
  const context = result?.comparison_context
  return Boolean(
    field &&
    Number.isFinite(Number(field.lat)) &&
    Number(field.lat) >= 20 &&
    Number(field.lat) <= 37 &&
    Number.isFinite(Number(field.lon)) &&
    Number(field.lon) >= -18 &&
    Number(field.lon) <= 0 &&
    Number.isFinite(Number(field.area_ha)) &&
    Number(field.area_ha) > 0 &&
    isRecord(inputs) &&
    typeof inputs.scenario_id === 'string' &&
    isRecord(inputs.field) &&
    typeof inputs.field.region_code === 'string' &&
    isRecord(inputs.priorities) &&
    ['water', 'nitrogen', 'resilience', 'soil', 'economy']
      .every((key) => (
        Number.isFinite(inputs.priorities[key]) &&
        inputs.priorities[key] >= 0 &&
        inputs.priorities[key] <= 1
      )) &&
    (inputs.current_rotation === null ||
      (Array.isArray(inputs.current_rotation) &&
        inputs.current_rotation.length === 3 &&
        inputs.current_rotation.every((crop) => typeof crop === 'string'))) &&
    result &&
    Array.isArray(result.comparison) &&
    result.comparison.every((row) => (
      isRecord(row) &&
      typeof row.scenario_id === 'string' &&
      typeof row.strategy_id === 'string' &&
      Array.isArray(row.rotation) &&
      ['water_total_mm', 'n_balance_kg', 'resilience_avg', 'soil_protection_avg', 'economic_potential_avg', 'score']
        .every((key) => Number.isFinite(row[key]))
    )) &&
    Array.isArray(result.ranked) &&
    result.ranked.every((entry) => isRecord(entry) && typeof entry.id === 'string') &&
    Array.isArray(result.strategies) &&
    result.strategies.every((strategy) => (
      isRecord(strategy) &&
      typeof strategy.id === 'string' &&
      typeof strategy.label === 'string' &&
      typeof strategy.rationale === 'string' &&
      Array.isArray(strategy.crop_evidence) &&
      strategy.crop_evidence.every((crop) => (
        isRecord(crop) &&
        typeof crop.code === 'string' &&
        typeof crop.name === 'string' &&
        Array.isArray(crop.documented_regions) &&
        Array.isArray(crop.source_ids)
      )) &&
      Array.isArray(strategy.limitations) &&
      Array.isArray(strategy.data_gaps)
    )) &&
    isRecord(context) &&
    Array.isArray(context.score_inputs) &&
    Array.isArray(context.data_gaps)
  )
}

export default function SimulationHistoryPanel({
  field,
  simulationInput,
  result,
  onRunLoaded,
}) {
  const [user, setUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(Boolean(supabase))
  const [runs, setRuns] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!supabase) return undefined

    let active = true
    supabase.auth.getSession()
      .then(({ data, error: sessionError }) => {
        if (!active) return
        if (sessionError) setError(`Account session could not be checked: ${sessionError.message}`)
        else setUser(data.session?.user ?? null)
      })
      .catch((sessionError) => {
        if (active) setError(`Account session could not be checked: ${sessionError.message}`)
      })
      .finally(() => {
        if (active) setAuthLoading(false)
      })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (!active) return
        setUser(session?.user ?? null)
        setError('')
        setMessage('')
      }
    )

    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])

  useEffect(() => {
    if (!supabase || !user) {
      setRuns([])
      setHistoryLoading(false)
      return undefined
    }

    let active = true
    setHistoryLoading(true)
    supabase
      .from('simulation_runs')
      .select('id, field, inputs, result, created_at')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(10)
      .then(({ data, error: queryError }) => {
        if (!active) return
        if (queryError) {
          setRuns([])
          setError(`Saved simulations could not be loaded: ${queryError.message}`)
          return
        }
        setRuns(data || [])
        setError('')
      })
      .catch((queryError) => {
        if (active) {
          setRuns([])
          setError(`Saved simulations could not be loaded: ${queryError.message}`)
        }
      })
      .finally(() => {
        if (active) setHistoryLoading(false)
      })

    return () => {
      active = false
    }
  }, [user, refreshKey])

  async function saveRun() {
    if (!supabase || !user || !field || !simulationInput || !result || !consent) return

    setBusy(true)
    setError('')
    setMessage('')
    try {
      const { error: saveError } = await supabase
        .from('simulation_runs')
        .insert({
          user_id: user.id,
          field,
          inputs: simulationInput,
          result,
          consented_at: new Date().toISOString(),
        })
      if (saveError) throw saveError
      setConsent(false)
      setMessage('Simulation saved to your account.')
      setRefreshKey((current) => current + 1)
    } catch (saveError) {
      setError(`Simulation was not saved: ${saveError.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function deleteRun(runId) {
    if (!supabase || !user || !window.confirm('Delete this saved simulation? This cannot be undone.')) return

    setBusy(true)
    setError('')
    setMessage('')
    try {
      const { error: deleteError } = await supabase
        .from('simulation_runs')
        .delete()
        .eq('id', runId)
        .eq('user_id', user.id)
      if (deleteError) throw deleteError
      setMessage('Saved simulation deleted.')
      setRefreshKey((current) => current + 1)
    } catch (deleteError) {
      setError(`Simulation was not deleted: ${deleteError.message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="simulation-history-panel" aria-labelledby="simulation-history-title">
      <div className="section-lead">
        <span className="eyebrow">Private account storage</span>
        <h2 id="simulation-history-title">Save and revisit a simulation.</h2>
        <p>Saving is optional. Only your signed-in account can access its saved runs.</p>
      </div>

      {!supabase ? (
        <p className="account-not-configured" role="status">
          Account storage is not configured. You can still use the simulator; saved runs require a configured Supabase project.
        </p>
      ) : authLoading ? (
        <p className="sub" role="status">Checking your account…</p>
      ) : !user ? (
        <p className="sub">
          Sign in or create an account on the <Link to="/data#account">farm profile page</Link> to save or retrieve simulations.
        </p>
      ) : (
        <>
          <p className="account-data-note">
            A saved run includes the field location and supplied soil values, simulation settings, and complete result. Saved runs are retained in your account until you delete them. The 10 most recent runs are shown here.
          </p>
          {field && simulationInput && result && (
            <div className="simulation-save-controls">
              <label className="account-consent">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                <span>I agree to save this field, simulation setup, and its results to my account.</span>
              </label>
              <button
                type="button"
                className="primary-button"
                onClick={saveRun}
                disabled={!consent || busy}
              >
                {busy ? 'Saving…' : 'Save this simulation'}
              </button>
            </div>
          )}
          {historyLoading ? (
            <p className="sub" role="status">Loading saved simulations…</p>
          ) : runs.length ? (
            <div className="simulation-history-list">
              {runs.map((run) => (
                <article className="simulation-history-item" key={run.id}>
                  <div>
                    <strong>{run.field?.region_name || 'Morocco'} · {run.inputs?.scenario_id || 'Saved scenario'}</strong>
                    <span>{Number.isNaN(new Date(run.created_at).getTime())
                      ? 'Date unavailable'
                      : new Date(run.created_at).toLocaleString()}</span>
                  </div>
                  <div className="simulation-history-actions">
                    <button
                      type="button"
                      className="account-secondary-button"
                      onClick={() => {
                        if (!isValidSavedRun(run)) {
                          setError('This saved simulation is incomplete and cannot be loaded.')
                          return
                        }
                        if (field && !window.confirm(
                          'Loading this simulation replaces the field and results currently open on this page. Continue?'
                        )) return
                        onRunLoaded(run)
                      }}
                      disabled={busy}
                    >
                      Load results
                    </button>
                    <button
                      type="button"
                      className="account-text-button"
                      onClick={() => deleteRun(run.id)}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="sub">{result ? 'No simulations have been saved to this account yet.' : 'Run a simulation to save it to your account.'}</p>
          )}
        </>
      )}

      {error && <p className="error-message" role="alert">{error}</p>}
      {message && <p className="account-status" role="status">{message}</p>}
    </section>
  )
}
