import { useEffect, useState } from 'react'
import { supabase } from './supabase'

function isValidSavedProfile(profile) {
  const field = profile?.field
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
    profile.baseline &&
    typeof profile.baseline === 'object' &&
    !Array.isArray(profile.baseline)
  )
}

export default function FarmAccountPanel({
  field,
  baseline,
  onProfileLoaded,
  onSignedOut,
}) {
  const [user, setUser] = useState(null)
  const [mode, setMode] = useState('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [authError, setAuthError] = useState('')
  const [authMessage, setAuthMessage] = useState('')
  const [profile, setProfile] = useState(null)
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileError, setProfileError] = useState('')
  const [profileMessage, setProfileMessage] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!supabase) return undefined

    let active = true
    supabase.auth.getSession()
      .then(({ data, error }) => {
        if (!active) return
        if (error) setAuthError(error.message)
        else setUser(data.session?.user ?? null)
      })
      .catch((error) => {
        if (active) setAuthError(error.message || 'Could not restore the account session.')
      })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (!active) return
        setUser(session?.user ?? null)
        setAuthError('')
        setAuthMessage('')
        if (event === 'SIGNED_OUT') onSignedOut()
      }
    )

    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])

  useEffect(() => {
    if (!supabase || !user) {
      setProfile(null)
      setProfileError('')
      return undefined
    }

    let active = true
    setProfileBusy(true)
    setProfileError('')
    setProfileMessage('')

    supabase
      .from('farm_profiles')
      .select('field, baseline, updated_at, consented_at')
      .eq('user_id', user.id)
      .maybeSingle()
      .then(({ data, error }) => {
        if (!active) return
        if (error) {
          setProfile(null)
          setProfileError(`Saved data could not be loaded: ${error.message}`)
          return
        }
        setProfile(data)
      })
      .catch((error) => {
        if (active) {
          setProfile(null)
          setProfileError(error.message || 'Saved data could not be loaded.')
        }
      })
      .finally(() => {
        if (active) setProfileBusy(false)
      })

    return () => {
      active = false
    }
  }, [user])

  async function submitAuth(event) {
    event.preventDefault()
    if (!supabase) return

    setAuthBusy(true)
    setAuthError('')
    setAuthMessage('')
    try {
      if (mode === 'sign-up') {
        const { data, error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        setAuthMessage(data.session
          ? 'Your account is ready.'
          : 'Account created. Check your email to confirm it, then sign in.')
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      }
      setPassword('')
    } catch (error) {
      setAuthError(error.message || 'Account authentication failed.')
    } finally {
      setAuthBusy(false)
    }
  }

  async function signOut() {
    if (!supabase) return
    setAuthBusy(true)
    setAuthError('')
    try {
      const { error } = await supabase.auth.signOut()
      if (error) throw error
      setProfile(null)
      setConsent(false)
      setProfileMessage('Signed out. Field details were cleared from this page.')
    } catch (error) {
      setAuthError(error.message || 'Could not sign out.')
    } finally {
      setAuthBusy(false)
    }
  }

  async function saveProfile() {
    if (!supabase || !user || !field || !consent) return
    setSaving(true)
    setProfileError('')
    setProfileMessage('')
    try {
      const savedProfile = {
        user_id: user.id,
        field,
        baseline,
        updated_at: new Date().toISOString(),
        consented_at: new Date().toISOString(),
      }
      const { error } = await supabase
        .from('farm_profiles')
        .upsert(savedProfile, { onConflict: 'user_id' })
      if (error) throw error
      setProfile(savedProfile)
      setConsent(false)
      setProfileMessage('Your field profile was saved to your account.')
    } catch (error) {
      setProfileError(`Your field profile was not saved: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  function loadSavedProfile() {
    if (!isValidSavedProfile(profile)) {
      setProfileError('The saved profile is incomplete and cannot be loaded.')
      return
    }
    if (field && !window.confirm(
      'Loading the saved profile replaces the field and baseline currently open on this page. Continue?'
    )) return
    onProfileLoaded(profile)
    setProfileMessage('Saved field profile loaded.')
    setProfileError('')
  }

  return (
    <section id="account" className="farm-account-panel" aria-labelledby="farm-account-title">
      <div className="farm-account-heading">
        <div>
          <span className="eyebrow">Private farm profile</span>
          <h2 id="farm-account-title">Save your field to an account.</h2>
          <p className="sub">
            Sign in to save or restore one field profile. Only the authenticated account can access its record.
          </p>
        </div>
        {user && (
          <div className="farm-account-user">
            <span>{user.email}</span>
            <button type="button" className="account-text-button" onClick={signOut} disabled={authBusy}>
              Sign out
            </button>
          </div>
        )}
      </div>

      {!supabase ? (
        <p className="account-not-configured" role="status">
          Account storage is not configured yet. Add the Supabase project URL and public publishable key to the frontend environment after creating the project.
        </p>
      ) : !user ? (
        <form className="farm-account-form" onSubmit={submitAuth}>
          <div className="account-input-grid">
            <label>
              Email
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete={mode === 'sign-up' ? 'new-password' : 'current-password'}
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
          </div>
          <div className="account-actions">
            <button type="submit" className="primary-button" disabled={authBusy}>
              {authBusy ? 'Please wait…' : mode === 'sign-up' ? 'Create account' : 'Sign in'}
            </button>
            <button
              type="button"
              className="account-text-button"
              onClick={() => {
                setMode((current) => current === 'sign-in' ? 'sign-up' : 'sign-in')
                setAuthError('')
                setAuthMessage('')
              }}
            >
              {mode === 'sign-up' ? 'Already have an account? Sign in' : 'Create an account'}
            </button>
          </div>
        </form>
      ) : (
        <div className="farm-account-storage">
          {profileBusy && <p className="sub" role="status">Checking for a saved field profile…</p>}
          {!profileBusy && profile && (
            <div className="saved-profile">
              <p>
                <strong>Saved field:</strong>{' '}
                {profile.field?.region_name || 'Morocco'} · {profile.field?.lat}, {profile.field?.lon}
              </p>
              <button
                type="button"
                className="account-secondary-button"
                onClick={loadSavedProfile}
                disabled={!isValidSavedProfile(profile)}
              >
                Load saved field
              </button>
            </div>
          )}
          {!profileBusy && !profile && !profileError && (
            <p className="sub">No field profile is saved to this account yet.</p>
          )}
          <p className="account-data-note">
            Saving stores the selected coordinates, region, area, irrigation, supplied soil values and farmer-reported baseline in Supabase. It does not change simulation scores. One profile is kept per account; saving again updates that profile.
          </p>
          <label className="account-consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>I agree to store these field details in my account. I understand that saving updates the one saved profile for this account.</span>
          </label>
          <button
            type="button"
            className="primary-button"
            onClick={saveProfile}
            disabled={!field || !consent || saving || profileBusy}
          >
            {saving ? 'Saving securely…' : profile ? 'Update saved field profile' : 'Save field profile'}
          </button>
        </div>
      )}

      {authError && <p className="error-message" role="alert">{authError}</p>}
      {profileError && <p className="error-message" role="alert">{profileError}</p>}
      {authMessage && <p className="account-status" role="status">{authMessage}</p>}
      {profileMessage && <p className="account-status" role="status">{profileMessage}</p>}
    </section>
  )
}
