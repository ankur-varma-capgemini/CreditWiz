import { ChevronRight, GraduationCap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { fetchItems, fetchLearningHome, itemHref, TYPE_LABEL, type Item, type LearningHome } from '../../lib/learning'
import { usePersona } from '../../lib/personaContext'
import { useHub } from '../../lib/hub'
import { BandSearch } from '../BandSearch'
import { PageBand } from '../PageBand'
import { ItemCard } from './ItemCard'
import { ProviderSearch } from './ProviderSearch'
import { ProviderShelves } from './ProviderShelves'

// Rows about this person, in the order the backend gives them: required, continue, recommended for their role.
const PERSONAL = new Set(['required', 'continue', 'role'])

function LearningSection({ section }: { section: LearningHome['sections'][number] }) {
  return (
    <section className={`lsection lsection--${section.id}`}>
      <h2 className="section-title">{section.title}</h2>
      <p className="section-sub">{section.subtitle}</p>
      {section.items.length ? (
        <div className="item-grid">
          {section.items.map((i) => (
            <ItemCard key={i.id} item={i} />
          ))}
        </div>
      ) : (
        <p className="muted">You're up to date.</p>
      )}
    </section>
  )
}

export function LearningPage() {
  const { derived } = usePersona()
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const [data, setData] = useState<{ key: string; home: LearningHome; items: Item[] } | null>(null)
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const pathId = params.get('path') ?? ''
  const mode = pathname.split('/')[2] ?? ''
  const type =
    mode === 'best-practices'
      ? 'best-practice'
      : mode === 'docs'
        ? 'docs'
        : mode === 'quick-reference'
          ? 'quick-reference'
          : (params.get('type') ?? '')
  const q = params.get('q') ?? ''
  const navigate = useNavigate()
  const { pillars } = useHub()
  const search = pillars.find((p) => p.id === 'learning')?.search
  // What is typed in the bar; the catalog only changes when it is submitted.
  const [draft, setDraft] = useState(q)
  useEffect(() => setDraft(q), [q])
  const status = params.get('status') ?? ''
  const source = params.get('source') ?? ''
  const key = [derived.id, pathId, mode, type, q, status, source, attempt].join('|')
  useEffect(() => {
    const ctrl = new AbortController()
    const timer = setTimeout(
      () => {
        Promise.all([fetchLearningHome(derived.id, ctrl.signal), fetchItems({ path: pathId, type, q, status, source }, ctrl.signal)])
          .then(([home, items]) => setData({ key, home, items }))
          .catch((e: unknown) => {
            if (!isAbort(e)) setFailure({ key, message: e instanceof Error ? e.message : 'Could not load learning' })
          })
      },
      q ? 180 : 0,
    )
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [key, derived.id, pathId, type, q, status, source])
  const current = data?.key === key ? data : null
  const error = failure?.key === key ? failure.message : ''
  const home = current?.home
  // The person's own rows lead the page; the type sections are a browse index below.
  const personal = (home?.sections ?? []).filter((s) => PERSONAL.has(s.id))
  const browseIndex = (home?.sections ?? []).filter((s) => !PERSONAL.has(s.id))
  const selectedPath = home?.paths.find((p) => p.id === pathId)
  const browse = !!pathId || (!!mode && mode !== 'paths')
  const title = pathId
    ? (selectedPath?.title ?? 'Learning path')
    : mode === 'paths'
      ? 'Role-based paths'
      : mode === 'catalog'
        ? 'Learning catalog'
        : mode === 'docs'
          ? 'Product documentation'
          : mode === 'best-practices'
            ? 'Best practices'
            : mode === 'quick-reference'
              ? 'Quick references'
              : 'Learning'
  function filter(name: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    setParams(next, { replace: name === 'q' })
  }
  // A search from "For you" or the paths overview lands on the catalog, which
  // is where every item can be listed; inside a browse view it narrows that view.
  function runSearch(value: string) {
    const trimmed = value.trim()
    if (!trimmed) return
    setDraft(trimmed)
    if (browse) filter('q', trimmed)
    else navigate(`/learning/catalog?q=${encodeURIComponent(trimmed)}`)
  }
  return (
    <div className="content">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} />
        <Link to="/learning">Learning</Link>
        {mode && (
          <>
            <ChevronRight size={16} />
            <span>{title}</span>
          </>
        )}
      </nav>
      <PageBand
        compact
        kicker={derived.label}
        title={title}
        // Only a selected path keeps a lead: it describes that path. The generic
        // line under the title is gone now that the search bar says what to do.
        lead={selectedPath?.blurb}
        aside={
          <Link to="/learning/me" className="band__action">
            <GraduationCap size={16} /> My learning
          </Link>
        }
      >
        <BandSearch
          value={draft}
          onChange={setDraft}
          onSearch={runSearch}
          onClear={() => {
            setDraft('')
            if (q) filter('q', '')
          }}
          placeholder={search?.placeholder ?? 'Search learning'}
          label="Search learning"
          action={search?.action ?? 'Find learning'}
          examples={q ? [] : (search?.examples ?? [])}
        />
        <nav className="pathbar pathbar--onband" aria-label="Learning views">
          {[
            ['', 'For you'],
            ['paths', 'Role-based paths'],
            ['catalog', 'Catalog'],
            ['best-practices', 'Best practices'],
            ['docs', 'Product docs'],
            ['quick-reference', 'Quick references'],
          ].map(([p, label]) => (
            // A selected path lives under Role-based paths, so that tab stays lit.
            <Link
              key={p}
              className={`pathbar__item${(pathId ? p === 'paths' : mode === p) ? ' is-active' : ''}`}
              to={`/learning${p ? '/' + p : ''}`}
            >
              {label}
            </Link>
          ))}
        </nav>
      </PageBand>
      {browse && (
        <div className="catalog-filters">
          {!pathId && mode === 'catalog' && (
            <label className="field">
              Content type
              <select value={type} onChange={(e) => filter('type', e.target.value)}>
                <option value="">All types</option>
                {Object.entries(TYPE_LABEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          )}
          {!pathId && mode === 'catalog' && (
            <label className="field">
              Provider
              <select value={source} onChange={(e) => filter('source', e.target.value)}>
                <option value="">All providers</option>
                <option value="Pluralsight">Pluralsight</option>
                <option value="Microsoft Learn">Microsoft Learn</option>
              </select>
            </label>
          )}
          <label className="field">
            Progress
            <select value={status} onChange={(e) => filter('status', e.target.value)}>
              <option value="">All progress</option>
              <option value="not_started">Not started</option>
              <option value="in_progress">In progress</option>
              <option value="completed">Completed</option>
            </select>
          </label>
        </div>
      )}
      {error ? (
        <div className="state state--error" role="alert">
          {error} <button onClick={() => setAttempt((a) => a + 1)}>Retry</button>
        </div>
      ) : !current ? (
        <div className="state" role="status">
          Loading learning…
        </div>
      ) : (
        <>
          {/* What this person should do first: required, in progress, then
              recommended for their role across every source. */}
          {!mode && !pathId && personal.map((s) => <LearningSection key={s.id} section={s} />)}
          {!mode && !pathId && <ProviderShelves persona={derived.id} />}
          {(!mode || mode === 'paths') && !pathId && (
            <section>
              <h2 className="section-title">Paths for {home?.persona_label}</h2>
              <div className="path-grid">
                {home?.role_paths.map((p) => (
                  <article className="pathcard" key={p.id}>
                    <h3 className="pathcard__title">{p.title}</h3>
                    <p className="pathcard__blurb">{p.blurb}</p>
                    <div className="pathcard__progress">
                      <span className="pathcard__bar" aria-hidden="true">
                        <span style={{ width: `${p.total_steps ? (p.completed_steps / p.total_steps) * 100 : 0}%` }} />
                      </span>
                      <span className="pathcard__count">
                        {p.completed_steps} of {p.total_steps} steps
                      </span>
                    </div>
                    <div className="pathcard__actions">
                      {p.next_item_id && (
                        <Link className="btn btn--inline" to={itemHref(p.next_item_id)}>
                          Continue path
                        </Link>
                      )}
                      <Link className="textlink" to={`/learning/paths?path=${p.id}`}>
                        View steps
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
              {mode === 'paths' && (
                <>
                  <h2 className="section-title">All available paths</h2>
                  <div className="pathbar">
                    {home?.paths.map((p) => (
                      <Link className="pathbar__item" key={p.id} to={`/learning/paths?path=${p.id}`}>
                        {p.title}
                      </Link>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}
          {browse && (
            <>
              {selectedPath && (
                <p>
                  {selectedPath.completed_steps} / {selectedPath.total_steps} completed · Follow the numbered sequence. Prerequisites are
                  shown on each item.
                </p>
              )}
              {q && !pathId && <h2 className="section-title">In the AI Hub catalog</h2>}
              {current.items.length ? (
                <div className="item-grid">
                  {current.items.map((i) => (
                    <ItemCard key={i.id} item={i} />
                  ))}
                </div>
              ) : (
                <div className="state">{q ? `Nothing in the hub's catalog matches “${q}”.` : 'No learning matches these filters.'}</div>
              )}
              {/* One search bar for all: the same words, in Pluralsight's and Microsoft Learn's own libraries. */}
              {q && !pathId && <ProviderSearch q={q} source={source} catalog={current.items} />}
            </>
          )}
          {!mode && !pathId && browseIndex.map((s) => <LearningSection key={s.id} section={s} />)}
        </>
      )}
    </div>
  )
}
