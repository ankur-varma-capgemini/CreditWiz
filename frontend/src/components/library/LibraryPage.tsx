import { ChevronRight, LayoutTemplate, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { useCreate } from '../../lib/create'
import { queryStems } from '../../lib/hubSearch'
import {
  SORTS,
  fetchLibrary,
  fetchMyDeskLibrary,
  setSaved,
  type LibraryPage as Library,
  type PromptCard,
  type Relation,
  type Sort,
} from '../../lib/prompts'
import { BandSearch } from '../BandSearch'
import { PageBand } from '../PageBand'
import { PromptTile } from './PromptTile'

interface Filters {
  q: string
  sort: Sort
  category: string
  relation: Relation | ''
}

/** Search, in the browser, with Nexus's word-start matching: a prompt needs
 *  half of the request's words; a word in its title counts twice. */
function filterPrompts(list: PromptCard[], { q, sort, category, relation }: Filters): PromptCard[] {
  let out = list.filter(
    (p) => (!category || p.category === category) && (!relation || p.relation === relation) && (sort !== 'saved' || p.saved),
  )
  const stems = queryStems(q)
  if (stems.length) {
    const starts = stems.map((s) => new RegExp(`\\b${s}`))
    const needed = Math.ceil(stems.length / 2)
    out = out
      .map((p) => {
        const text = `${p.title} ${p.description} ${p.category} ${p.tags.join(' ')}`.toLowerCase()
        const hits = starts.filter((r) => r.test(text)).length
        const inTitle = starts.filter((r) => r.test(p.title.toLowerCase())).length
        return { p, score: hits >= needed ? hits + inTitle : 0 }
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score || b.p.uses - a.p.uses)
      .map((x) => x.p)
  }
  if (sort === 'used' || (sort === 'relevance' && !stems.length)) return [...out].sort((a, b) => b.uses - a.uses)
  if (sort === 'rated') return [...out].sort((a, b) => b.rating - a.rating || b.ratings - a.ratings)
  if (sort === 'new') return [...out].sort((a, b) => b.updated.localeCompare(a.updated))
  return out
}

export function LibraryPage() {
  const { open } = useCreate()
  // '' asks the server for the viewer's own desk.
  const [desk, setDesk] = useState('')
  const [lib, setLib] = useState<Library | null>(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<Sort>('relevance')
  const [category, setCategory] = useState('')
  const [relation, setRelation] = useState<Relation | ''>('')

  useEffect(() => {
    const ctrl = new AbortController()
    ;(desk ? fetchLibrary(desk, ctrl.signal) : fetchMyDeskLibrary(ctrl.signal))
      .then((l) => {
        setLib(l)
        setError('')
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'The prompt library could not load.')
      })
    return () => ctrl.abort()
  }, [desk])

  const shown = useMemo(() => filterPrompts(lib?.prompts ?? [], { q, sort, category, relation }), [lib, q, sort, category, relation])
  const onOwnDesk = !!lib?.desk && lib.showing === lib.desk.id

  function toggleSave(p: PromptCard) {
    const flip = (saved: boolean) =>
      setLib((l) => (l ? { ...l, prompts: l.prompts.map((x) => (x.id === p.id ? { ...x, saved } : x)) } : l))
    flip(!p.saved)
    setSaved(p.id, !p.saved).catch(() => flip(p.saved))
  }

  return (
    <div className="content">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <span>Prompts &amp; Skills</span>
      </nav>

      <PageBand
        kicker="Prompts & Skills"
        title="Prompt library"
        compact
        aside={
          <span className="lib-actions">
            <Link className="btn-outline" to="/library/templates">
              <LayoutTemplate size={16} strokeWidth={2.2} /> Templates
            </Link>
            <button type="button" className="btn btn--inline" onClick={() => open({ kind: 'prompt' })}>
              <Plus size={16} strokeWidth={2.4} /> Create a prompt
            </button>
          </span>
        }
      >
        <BandSearch
          value={q}
          onChange={setQ}
          onSearch={(v) => setQ(v)}
          onClear={() => setQ('')}
          placeholder="Search prompts, e.g. pitch deck outline"
          label="Search the prompt library"
          action="Search"
          examples={q ? [] : ['Pitch deck outline', 'Covenant scan', 'Stress test']}
        />
      </PageBand>

      <p className="lib-lead">
        Every prompt here passed review by the Data Privacy Office.{' '}
        {lib?.desk ? `Showing ${onOwnDesk ? `your desk, ${lib.desk.label.toLowerCase()}s` : 'another view'} first.` : ''}
      </p>

      <div className="lib-controls">
        <label className="sr-only" htmlFor="lib-desk">
          Desk
        </label>
        <select
          id="lib-desk"
          className="lib-select"
          value={lib?.showing ?? ''}
          onChange={(e) => {
            setDesk(e.target.value)
            setRelation('')
          }}
        >
          {lib?.desks.map((d) => (
            <option key={d.id} value={d.id}>
              {lib.desk?.id === d.id ? `${d.label}s (your desk)` : `${d.label}s`}
            </option>
          ))}
          <option value="all">All desks</option>
        </select>
        {onOwnDesk && (
          <>
            <label className="sr-only" htmlFor="lib-rel">
              Made by
            </label>
            <select id="lib-rel" className="lib-select" value={relation} onChange={(e) => setRelation(e.target.value as Relation | '')}>
              <option value="">Made by anyone</option>
              <option value="team">Made by your team</option>
              <option value="dept">Made in your department</option>
              <option value="other">Made on another desk</option>
            </select>
          </>
        )}
        <div className="lib-tabs" role="group" aria-label="Sort and filter">
          {SORTS.map(([value, label]) => (
            <button key={value} type="button" aria-pressed={sort === value} onClick={() => setSort(value)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="lib-chips" role="group" aria-label="Category">
        <button type="button" className="lib-chip" aria-pressed={!category} onClick={() => setCategory('')}>
          All categories
        </button>
        {lib?.categories.map((c) => (
          <button key={c} type="button" className="lib-chip" aria-pressed={category === c} onClick={() => setCategory(category === c ? '' : c)}>
            {c}
          </button>
        ))}
      </div>

      {error && (
        <p className="state state--error" role="alert">
          {error}
        </p>
      )}
      {!lib && !error && <div className="skeleton" style={{ height: 320 }} />}
      {lib && (
        <>
          <p className="lib-count" aria-live="polite">
            {shown.length} {shown.length === 1 ? 'prompt' : 'prompts'}
            {q.trim() && <> for &ldquo;{q.trim()}&rdquo;</>}
          </p>
          {shown.length ? (
            <div className="lib-grid">
              {shown.map((p) => (
                <PromptTile key={p.id} p={p} onToggleSave={toggleSave} />
              ))}
            </div>
          ) : (
            <section className="panel lib-empty">
              <h2 className="panel__title">{sort === 'saved' ? 'Nothing saved yet' : 'No validated prompt covers that yet'}</h2>
              <p className="panel__text">
                {sort === 'saved'
                  ? 'Save a prompt with its bookmark and it appears here and in My library.'
                  : 'If you have written the same analysis three times this month, that is a prompt worth sharing.'}
              </p>
              {sort !== 'saved' && (
                <button type="button" className="btn btn--inline" onClick={() => open({ kind: 'prompt' })}>
                  <Plus size={16} strokeWidth={2.4} /> Draft one
                </button>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}
