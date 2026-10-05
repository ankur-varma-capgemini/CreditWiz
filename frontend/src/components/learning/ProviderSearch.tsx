import { BookOpen, Clock, ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { duration, readerHref, searchProviders, type Item, type ProviderResults } from '../../lib/learning'

/** One address per page: no locale, query, fragment or trailing slash. */
function page(url: string) {
  return url
    .toLowerCase()
    .split(/[?#]/)[0]
    .replace(/\/[a-z]{2}-[a-z]{2}\//, '/')
    .replace(/\/+$/, '')
}

const STATE: Record<ProviderResults['state'], { label: string; tone: string }> = {
  live: { label: 'Live', tone: '' },
  sample: { label: 'Not connected', tone: 'status--deprecated' },
  blocked: { label: 'Blocked', tone: 'status--beta' },
}

/**
 * The second half of the Learning search: the same words, searched live in
 * Pluralsight's and Microsoft Learn's own libraries. Anything already in the
 * hub's catalogue is shown above, so it is left out here.
 */
export function ProviderSearch({ q, source, catalog }: { q: string; source: string; catalog: Item[] }) {
  const [found, setFound] = useState<{ q: string; groups: ProviderResults[] } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (q.trim().length < 2) return
    const ctrl = new AbortController()
    searchProviders(q, ctrl.signal)
      .then((groups) => {
        setError('')
        setFound({ q, groups })
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'The providers did not answer.')
      })
    return () => ctrl.abort()
  }, [q])

  if (q.trim().length < 2) return null
  const known = new Set(catalog.map((i) => page(i.url)).filter(Boolean))
  const groups = found?.q === q ? found.groups.filter((g) => !source || g.provider === source) : null

  return (
    <section className="psearch" aria-live="polite" aria-labelledby="psearch-title">
      <h2 className="section-title" id="psearch-title">
        {source ? `From ${source}` : 'From Pluralsight and Microsoft Learn'}
      </h2>
      <p className="section-sub">Searched live in each provider's own library, beyond the courses curated in the hub.</p>
      {error ? (
        <p className="muted" role="alert">
          {error}
        </p>
      ) : !groups ? (
        <div className="psearch__groups">
          <div className="skeleton" style={{ height: 160 }} />
          <div className="skeleton" style={{ height: 160 }} />
        </div>
      ) : (
        <div className="psearch__groups">
          {groups.map((g) => {
            const results = g.results.filter((r) => !known.has(page(r.url)))
            return (
              <div key={g.provider} className="psearch__group">
                <div className="psearch__head">
                  <span className={`provider provider--${g.provider === 'Pluralsight' ? 'pluralsight' : 'mslearn'}`}>{g.provider}</span>
                  <Link to="/integrations" className={`status ${STATE[g.state].tone}`}>
                    {STATE[g.state].label}
                  </Link>
                </div>
                {g.note && <p className="psearch__note">{g.note}</p>}
                {g.state === 'live' && results.length === 0 && (
                  <p className="psearch__note">No other {g.provider} results for “{q}”.</p>
                )}
                {results.length > 0 && (
                  <ul className="psearch__list">
                    {results.map((r) => (
                      <li key={r.url}>
                        {r.read_in_hub ? (
                          <Link to={readerHref(r.url)} className="psearch__hit">
                            <span className="psearch__title">{r.title}</span>
                            {r.excerpt && <span className="psearch__excerpt">{r.excerpt}</span>}
                            <span className="psearch__meta">
                              <BookOpen size={13} strokeWidth={2.2} /> Read in the hub
                            </span>
                          </Link>
                        ) : (
                          <a href={r.url} target="_blank" rel="noreferrer" className="psearch__hit">
                            <span className="psearch__title">{r.title}</span>
                            {r.excerpt && <span className="psearch__excerpt">{r.excerpt}</span>}
                            <span className="psearch__meta">
                              {r.level && <span>{r.level}</span>}
                              {r.duration_seconds > 0 && (
                                <span>
                                  <Clock size={13} strokeWidth={2.2} /> {duration(r.duration_seconds)}
                                </span>
                              )}
                              <span>
                                Open in Pluralsight <ExternalLink size={12} strokeWidth={2.2} />
                              </span>
                            </span>
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
