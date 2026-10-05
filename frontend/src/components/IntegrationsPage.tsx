import { Check, ChevronRight, Copy, ExternalLink, LogIn, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { isAbort } from '../lib/api'
import { fetchIntegrations, signInWithMicrosoft, STATE_LABEL, type Integration } from '../lib/integrations'
import { PageBand } from './PageBand'
import '../integrations.css'

const TONE: Record<Integration['state'], string> = {
  live: '',
  sample: 'status--deprecated',
  signed_out: 'status--in_development',
  blocked: 'status--beta',
  not_configured: 'status--deprecated',
}

/** Plain text of everything still missing, ready to paste into an email to MUFG. */
function request(list: Integration[]) {
  return list
    .map((i) => ({ i, open: i.needs.filter((n) => !n.met) }))
    .filter(({ open }) => open.length)
    .map(({ i, open }) => [`${i.name}:`, ...open.map((n) => `- ${n.what}${n.setting ? ` (${n.setting})` : ''}`)].join('\n'))
    .join('\n\n')
}

/**
 * Which connected systems are live for you, and exactly what blocks the rest.
 * The hub works on sample content meanwhile; this page is where it says why.
 */
export function IntegrationsPage() {
  const [params] = useSearchParams()
  const [list, setList] = useState<Integration[] | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const outcome = params.get('entra')

  useEffect(() => {
    const ctrl = new AbortController()
    fetchIntegrations(ctrl.signal)
      .then(setList)
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Could not load integrations.')
      })
    return () => ctrl.abort()
  }, [])

  async function copy() {
    if (!list) return
    try {
      await navigator.clipboard.writeText(request(list))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  const missing = list ? request(list) : ''

  return (
    <div className="content">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <span>Integrations</span>
      </nav>
      <PageBand
        compact
        kicker="Platform"
        title="Integrations"
        lead="Which connected systems are live for you, and what is blocking the rest. Until a system is live, the hub shows sample content and says so."
      />

      {outcome === 'failed' && (
        <div className="state state--error" role="alert">
          Microsoft sign-in did not complete. The reason Microsoft gave is under Microsoft Entra ID sign-in below.
        </div>
      )}
      {outcome === 'not_configured' && (
        <div className="state state--error" role="alert">
          Microsoft sign-in is not set up yet. It needs MUFG&apos;s app registration, listed below.
        </div>
      )}
      {error && (
        <div className="state state--error" role="alert">
          {error}
        </div>
      )}

      {missing && (
        <section className="panel integ-ask">
          <div>
            <h2 className="panel__title">What to ask MUFG for</h2>
            <p className="panel__text">Everything still missing, as a list you can paste into an email.</p>
          </div>
          <button type="button" className="btn-outline" onClick={() => void copy()}>
            {copied ? <Check size={14} strokeWidth={2.6} /> : <Copy size={14} strokeWidth={2.2} />} {copied ? 'Copied' : 'Copy the list'}
          </button>
        </section>
      )}

      <div className="integ-list">
        {(list ?? []).map((i) => (
          <article key={i.id} className="panel integ" aria-labelledby={`integ-${i.id}`}>
            <header className="integ__head">
              <h2 className="integ__name" id={`integ-${i.id}`}>
                {i.name}
              </h2>
              <span className={`status ${TONE[i.state]}`}>{STATE_LABEL[i.state]}</span>
            </header>
            <p className="panel__text">{i.summary}</p>
            {i.blocking && (
              <p className="integ__blocking">
                <strong>Reason given:</strong> <code>{i.blocking}</code>
              </p>
            )}
            {i.id === 'entra' && i.state !== 'live' && (
              <button
                type="button"
                className="btn btn--inline"
                disabled={i.state === 'not_configured'}
                onClick={() => signInWithMicrosoft('/community')}
              >
                <LogIn size={15} strokeWidth={2.2} /> Sign in with Microsoft
              </button>
            )}
            <div className="integ__cols">
              <div>
                <h3 className="integ__h">What it needs</h3>
                <ul className="integ__needs">
                  {i.needs.map((n) => (
                    <li key={n.what} className={n.met ? 'is-met' : ''}>
                      {n.met ? <Check size={14} strokeWidth={2.8} aria-label="In place" /> : <X size={14} strokeWidth={2.8} aria-label="Missing" />}
                      <span>
                        {n.what}
                        {n.setting && <code>{n.setting}</code>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="integ__h">What the hub calls</h3>
                <ul className="integ__calls">
                  {i.calls.map((c) => (
                    <li key={c}>
                      <code>{c}</code>
                    </li>
                  ))}
                </ul>
                <p className="integ__code">
                  Code: <code>{i.code}</code>
                </p>
                <p className="integ__docs">
                  {i.docs.map((d) => (
                    <a key={d.url} href={d.url} target="_blank" rel="noreferrer">
                      {d.label} <ExternalLink size={12} strokeWidth={2.4} />
                    </a>
                  ))}
                </p>
              </div>
            </div>
          </article>
        ))}
        {!list && !error && (
          <>
            <div className="skeleton" style={{ height: 220, marginBottom: 16 }} />
            <div className="skeleton" style={{ height: 220 }} />
          </>
        )}
      </div>
    </div>
  )
}
