import { ArrowRight, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { isAbort, searchHub } from '../lib/api'
import { useHub } from '../lib/hub'
import { matchSections } from '../lib/hubSearch'
import { pillarBasePath, type SearchResult } from '../lib/types'
import { BandSearch } from './BandSearch'
import { PageBand } from './PageBand'
import { NotFound } from './SimplePages'

export function PillarPage() {
  const { pillars } = useHub()
  const { pathname } = useLocation()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const [draft, setDraft] = useState(q)
  useEffect(() => setDraft(q), [q])

  // A planned pillar has no engine of its own yet. Until its agent exists, a
  // search here answers from what is real: this pillar's own sections, and the
  // live hub search across Discover and Learning. Stated on the page, so the
  // bar never implies an answer the pillar cannot give.
  const [hub, setHub] = useState<{ q: string; results: SearchResult[] } | null>(null)
  useEffect(() => {
    if (!q.trim()) return
    const ctrl = new AbortController()
    searchHub(q, ctrl.signal)
      .then((results) => setHub({ q, results }))
      .catch((e: unknown) => {
        if (!isAbort(e)) setHub({ q, results: [] })
      })
    return () => ctrl.abort()
  }, [q])

  const base = '/' + (pathname.split('/')[1] ?? '')
  const pillar = pillars.find((p) => pillarBasePath(p) === base)
  if (!pillar) return <NotFound />

  const current = pillar.sections.find((s) => s.href === pathname)
  const sectionHits = matchSections([pillar], q).map((h) => h.section)
  const hubHits = hub?.q === q ? hub.results : null

  function runSearch(value: string) {
    const trimmed = value.trim()
    if (!trimmed) return
    setDraft(trimmed)
    const next = new URLSearchParams(params)
    next.set('q', trimmed)
    setParams(next, { replace: true })
  }

  function clearSearch() {
    setDraft('')
    const next = new URLSearchParams(params)
    next.delete('q')
    setParams(next, { replace: true })
  }

  return (
    <div className="content">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        {current ? <Link to={base}>{pillar.short_title}</Link> : <span>{pillar.short_title}</span>}
        {current && (
          <>
            <ChevronRight size={16} strokeWidth={2.2} />
            <span>{current.title}</span>
          </>
        )}
      </nav>

      <PageBand
        kicker={current ? pillar.short_title : undefined}
        title={current ? current.title : pillar.short_title}
        aside={<span className="soon-badge">Coming soon</span>}
        compact
      >
        {pillar.search && (
          <BandSearch
            value={draft}
            onChange={setDraft}
            onSearch={runSearch}
            onClear={clearSearch}
            placeholder={pillar.search.placeholder}
            label={`Search ${pillar.short_title}`}
            action={pillar.search.action}
            examples={q ? [] : pillar.search.examples}
          />
        )}
      </PageBand>

      {q && (
        <section className="pillar-results" aria-live="polite">
          <p className="pillar-results__note">
            {pillar.short_title} search is coming soon. Here are matching {pillar.short_title} sections and results from
            Discover and Learning.
          </p>
          <div className="home-cards">
            <div className="panel home-card">
              <h2 className="home-card__title">In {pillar.short_title}</h2>
              {sectionHits.length ? (
                <ul className="home-list">
                  {sectionHits.map((s) => (
                    <li key={s.href}>
                      <Link className="home-row" to={s.href}>
                        <span className="home-row__title">{s.title}</span>
                        <span className="home-row__sub">{s.blurb}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No {pillar.short_title} section matches “{q}”.</p>
              )}
            </div>
            <div className="panel home-card">
              <h2 className="home-card__title">Across Nexus</h2>
              {hubHits === null ? (
                <div className="skeleton" style={{ height: 96 }} />
              ) : hubHits.length ? (
                <ul className="home-list">
                  {hubHits.slice(0, 5).map((r) => (
                    <li key={r.href}>
                      <Link className="home-row" to={r.href}>
                        <span className="home-row__title">
                          <span className={`search__kind search__kind--${r.kind}`}>{r.kind}</span>
                          {r.title}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">Nothing in Discover or Learning matches “{q}”.</p>
              )}
            </div>
          </div>
        </section>
      )}

      {current ? (
        <section className="panel">
          <h2 className="panel__title">{current.title}</h2>
          <p className="panel__text">
            {current.blurb} This area is coming soon.
          </p>
          <Link className="mcard__link" to={base}>
            Back to {pillar.short_title} <ArrowRight strokeWidth={2.4} />
          </Link>
        </section>
      ) : null}

      <h2 className="section-title">{current ? `More in ${pillar.short_title}` : 'What’s coming'}</h2>
      <section className="more-grid" aria-label={`${pillar.short_title} sections`}>
        {pillar.sections
          .filter((s) => s.href !== current?.href)
          .map((s) => (
            <Link key={s.href} to={s.href} className={`scard scard--${pillar.tone}`}>
              <span className="scard__title">{s.title}</span>
              <span className="scard__blurb">{s.blurb}</span>
              <span className="scard__go">
                Open <ArrowRight size={18} strokeWidth={2.4} />
              </span>
            </Link>
          ))}
      </section>
    </div>
  )
}
