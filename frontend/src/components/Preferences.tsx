import { useEffect, useState } from 'react'
import { fetchPreferences, getJson, isAbort, requestJson, type Preferences as Values } from '../lib/api'
import { useHub } from '../lib/hub'
type AccessRequest = { id: string; agent_name: string; status: string; reason: string }
export function Preferences() {
  const { domains } = useHub()
  const [value, setValue] = useState<Values | null>(null)
  const [requests, setRequests] = useState<AccessRequest[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const ctrl = new AbortController()
    Promise.all([fetchPreferences(ctrl.signal), getJson<AccessRequest[]>('/api/access-requests', ctrl.signal)])
      .then(([prefs, rows]) => {
        setValue(prefs)
        setRequests(rows)
        setError('')
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Could not load preferences')
      })
    return () => ctrl.abort()
  }, [attempt])
  async function save() {
    setBusy(true)
    setMessage('')
    setError('')
    try {
      await requestJson('/api/preferences', { method: 'PUT', body: JSON.stringify(value) })
      setMessage('Preferences saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save preferences')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <section className="panel">
        <h2 className="panel__title">Preferences</h2>
        {error && (
          <p role="alert">
            {error} <button onClick={() => setAttempt((a) => a + 1)}>Reload</button>
          </p>
        )}
        {value && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void save()
            }}
          >
            <label className="field">
              Default business domain
              <select value={value.default_domain} onChange={(e) => setValue({ ...value, default_domain: e.target.value })}>
                {domains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field field--row">
              <input
                type="checkbox"
                checked={value.show_learning_reminders}
                onChange={(e) => setValue({ ...value, show_learning_reminders: e.target.checked })}
              />{' '}
              Show learning announcements in Nexus
            </label>
            <button className="btn btn--inline" disabled={busy}>
              {busy ? 'Saving…' : 'Save preferences'}
            </button>
            {message && <p role="status">{message}</p>}
          </form>
        )}
      </section>
      <section className="panel">
        <h2 className="panel__title">Your access requests</h2>
        <p>Your access requests and where each one stands.</p>
        {requests.length ? (
          requests.map((r) => (
            <div key={r.id}>
              <strong>{r.agent_name}</strong> · {r.status}
              <p>{r.reason}</p>
            </div>
          ))
        ) : (
          <p>No requests yet.</p>
        )}
      </section>
    </>
  )
}
