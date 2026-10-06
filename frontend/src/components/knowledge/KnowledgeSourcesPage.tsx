import { BookOpen, ChevronRight, FileText, FolderOpen, LifeBuoy, ListChecks, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import {
  SYSTEM_KIND_LABEL,
  fetchKnowledgeSources,
  type KnowledgeSources,
  type SystemKind,
} from '../../lib/knowledge'
import { Cover } from '../Cover'
import { PageBand } from '../PageBand'
import '../../knowledge.css'

const KIND_ICON: Record<SystemKind, LucideIcon> = {
  wiki: BookOpen,
  document_site: FolderOpen,
  work_tracking: ListChecks,
  service_management: LifeBuoy,
  document_store: FileText,
}

/** A value the owning team has not confirmed says so, rather than being guessed. */
function Confirmed({ value }: { value: string }) {
  return value ? <>{value}</> : <span className="tbc">To be confirmed</span>
}

export function KnowledgeSourcesPage() {
  const [sources, setSources] = useState<KnowledgeSources | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const ctrl = new AbortController()
    fetchKnowledgeSources(ctrl.signal)
      .then(setSources)
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Knowledge sources could not load.')
      })
    return () => ctrl.abort()
  }, [])

  const systemName = (id: string) => sources?.systems.find((s) => s.id === id)?.name ?? id

  return (
    <div className="content">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <Link to="/knowledge">Knowledge</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <span>Sources</span>
      </nav>
      <PageBand
        kicker="Knowledge"
        title="Knowledge sources"
        compact
        lead="The systems and document types that will feed the AI Hub, as the team listed them for Swim Lane 1. Nothing is connected yet: the hub links to these documents rather than reading them."
      />
      {error && (
        <p className="state state--error" role="alert">
          {error}
        </p>
      )}
      {!sources && !error && <div className="skeleton" style={{ height: 320 }} />}

      {sources && (
        <>
          <h2 className="section-title section-title--first">Where the content lives</h2>
          <ul className="ks-grid">
            {sources.systems.map((s) => {
              const Icon = KIND_ICON[s.kind]
              return (
                <li key={s.id} className="panel ks-card">
                  <div className="ks-card__head">
                    <Cover icon={Icon} size="tile" />
                    <div>
                      <h3 className="panel__title">{s.name}</h3>
                      <p className="ks-kind">{SYSTEM_KIND_LABEL[s.kind]}</p>
                    </div>
                  </div>
                  <p className="ks-feeds">
                    <span className="ks-label">Proposed use in the hub</span>
                    {s.feeds}
                  </p>
                  <dl className="ks-facts">
                    <dt>Status</dt>
                    <dd>
                      <span className={`ks-status ks-status--${s.connection}`}>
                        {s.connection === 'connected' ? 'Connected' : 'Not connected'}
                      </span>
                    </dd>
                    <dt>Owner</dt>
                    <dd>
                      <Confirmed value={s.owner} />
                    </dd>
                    <dt>Location</dt>
                    <dd>
                      <Confirmed value={s.location} />
                    </dd>
                  </dl>
                </li>
              )
            })}
          </ul>

          <h2 className="section-title">Document types</h2>
          <div className="ks-table-wrap">
            <table className="ks-table">
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col">What it is</th>
                  <th scope="col">Proposed use in the hub</th>
                  <th scope="col">Kept in</th>
                  <th scope="col">Owner</th>
                </tr>
              </thead>
              <tbody>
                {sources.document_types.map((d) => (
                  <tr key={d.id}>
                    <th scope="row">
                      <span className="ks-abbr">{d.abbreviation}</span>
                      <span className="ks-name">
                        <Confirmed value={d.name} />
                      </span>
                    </th>
                    <td data-label="What it is">
                      <Confirmed value={d.about} />
                    </td>
                    <td data-label="Proposed use in the hub">
                      <Confirmed value={d.feeds} />
                    </td>
                    <td data-label="Kept in">
                      <Confirmed value={d.lives_in.map(systemName).join(', ')} />
                    </td>
                    <td data-label="Owner">
                      <Confirmed value={d.owner} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="section-title">How the team groups its links</h2>
          <div className="ks-groups">
            {sources.link_groups.map((g) => (
              <section key={g.id} className="panel ks-group">
                <h3 className="panel__title">{g.name}</h3>
                <ul className="ks-group__list">
                  {g.systems.map((id) => (
                    <li key={id}>{systemName(id)}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <p className="ks-note">
            Listed from the team&apos;s Swim Lane 1 note. What each would feed in the hub is a proposal to agree with
            the owning teams; anything they have not confirmed says so.
          </p>
        </>
      )}
    </div>
  )
}
