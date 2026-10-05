import { LogIn } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getJson, isAbort, postJson, announceSessionChange } from '../lib/api'
import { signInWithMicrosoft } from '../lib/integrations'

export function SignIn({ onSignIn }: { onSignIn: () => void }) {
  const [options, setOptions] = useState<{ demo: boolean; microsoft: boolean; users: { id: string; name: string; role: string }[] } | null>(
    null,
  )
  const failed = new URLSearchParams(window.location.search).get('entra') === 'failed'
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const ctrl = new AbortController()
    getJson<typeof options>('/api/auth/options', ctrl.signal)
      .then(setOptions)
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Sign-in unavailable')
      })
    return () => ctrl.abort()
  }, [attempt])
  async function signIn(route: string, body: unknown) {
    setBusy(true)
    setError('')
    try {
      await postJson(route, body)
      announceSessionChange()
      onSignIn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not sign in')
    } finally {
      setBusy(false)
    }
  }
  return (
    <main className="signin">
      <div className="signin__brand">
        MUFG <span>AI Hub</span>
      </div>
      <h1>Welcome to the MUFG AI Hub</h1>
      <p>Discover agents and follow learning paths for your role.</p>
      {options && (
        <div className="signin__microsoft">
          <button type="button" className="btn" disabled={!options.microsoft} onClick={() => signInWithMicrosoft('/')}>
            <LogIn size={16} strokeWidth={2.2} /> Sign in with Microsoft
          </button>
          <p className="muted">
            {options.microsoft
              ? 'Your MUFG account. The hub then shows Viva Engage with your own permissions.'
              : "Needs MUFG's app registration in Microsoft Entra ID. Until then, use a demo account."}
          </p>
          {failed && (
            <p role="alert" className="state--error">
              Microsoft sign-in did not complete. Sign in with a demo account to see the reason under Integrations.
            </p>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="state--error">
          {error}
        </p>
      )}
      {!options && (
        <button
          className="btn btn--inline"
          onClick={() => {
            setError('')
            setAttempt((a) => a + 1)
          }}
        >
          Retry connection
        </button>
      )}
      {options?.demo ? (
        <>
          <h2>Choose a demo account</h2>
          <p className="muted">Local demonstration with sample content. Each account has its own saved progress and permissions.</p>
          <div className="signin__accounts">
            {options.users.map((u) => (
              <button key={u.id} disabled={busy} className="panel" onClick={() => void signIn('/api/auth/demo', { user_id: u.id })}>
                <strong>{u.name}</strong>
                <span>{u.role}</span>
              </button>
            ))}
          </div>
        </>
      ) : (
        options && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              const data = new FormData(e.currentTarget)
              void signIn('/api/auth/login', Object.fromEntries(data))
            }}
          >
            <label className="field">
              Email
              <input name="email" type="email" required autoComplete="username" />
            </label>
            <label className="field">
              Password
              <input name="password" type="password" required autoComplete="current-password" />
            </label>
            <button className="btn btn--inline" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )
      )}
    </main>
  )
}
