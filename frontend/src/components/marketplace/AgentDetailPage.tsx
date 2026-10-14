import { AccessRequestForm } from './AccessRequestForm'
import {
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
  MessageSquare,
  Rocket,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { formatDate } from '../../lib/format'
import { fetchAgentLearning, type Item } from '../../lib/learning'
import { track, type EventType } from '../../lib/context'
import { fetchKnowledgeSources, type KnowledgeSources } from '../../lib/knowledge'
import { ACCESS_LABEL, STATUS_LABEL, fetchAgent, fetchRelated, type Agent } from '../../lib/marketplace'
import { usePersona } from '../../lib/personaContext'
import { BackButton } from '../BackButton'
import { ItemCard } from '../learning/ItemCard'
import { NotFound } from '../SimplePages'
import { AgentCard } from './AgentCard'
import { FeedbackPrompt } from './FeedbackPrompt'
import '../../knowledge.css'

const PERSONA_LABEL: Record<string, string> = {
  business_user: 'Business users',
  compliance_user: 'Compliance users',
  risk_analyst: 'Risk analysts',
  operations_user: 'Operations users',
  developer: 'Developers',
}

/** "Hannah Weiss" -> "HW"; a team name when no person is confirmed. */
/** A value the owning team has not confirmed says so, rather than being guessed. */
function Unconfirmed({ text = 'To be confirmed' }: { text?: string }) {
  return <span className="tbc">{text}</span>
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

function ExtLink({
  href,
  event,
  agent,
  className,
  children,
}: {
  href: string
  event: EventType
  agent: Agent
  className: string
  children: React.ReactNode
}) {
  const { persona } = usePersona()
  return (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={() =>
        track('marketplace', event, {
          subject_id: agent.id,
          subject_type: 'agent',
          persona,
          topics: [...agent.business_domains, ...agent.capabilities],
        })
      }
    >
      {children}
    </a>
  )
}

export function AgentDetailPage() {
  const { id = '' } = useParams()
  const { persona } = usePersona()
  const [agent, setAgent] = useState<Agent | null | undefined>(undefined)
  const [related, setRelated] = useState<Agent[]>([])
  const [videos, setVideos] = useState<Item[]>([])
  // The document types and systems its documents are listed by.
  const [sources, setSources] = useState<KnowledgeSources | null | undefined>(undefined)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchKnowledgeSources(ctrl.signal)
      .then(setSources)
      .catch((err: unknown) => {
        if (!isAbort(err)) setSources(null)
      })
    return () => ctrl.abort()
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    setAgent(undefined)
    setVideos([])
    fetchAgent(id, ctrl.signal)
      .then((a) => {
        setAgent(a)
        track('marketplace', 'view', {
          subject_id: a.id,
          subject_type: 'agent',
          persona,
          topics: [...a.business_domains, ...a.capabilities],
        })
      })
      .catch((err: unknown) => {
        if (!isAbort(err)) setAgent(null)
      })
    fetchRelated(id, ctrl.signal)
      .then(setRelated)
      .catch(() => setRelated([]))
    fetchAgentLearning(id, persona, ctrl.signal)
      .then(setVideos)
      .catch(() => setVideos([]))
    return () => ctrl.abort()
    // persona intentionally excluded: viewing is logged once per agent load
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, persona])

  if (agent === null) return <NotFound />
  if (agent === undefined) {
    return (
      <div className="content">
        <div className="skeleton" style={{ height: 24, width: 320, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 160, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 320 }} />
      </div>
    )
  }

  const forYou = agent.personas.includes(persona)
  // The primary action follows the agent's declared access type. It used to
  // collapse to "Request access" for every sample listing -- so an agent whose
  // card said "Open" asked the user to request it on the next page.
  const access = agent.access.type
  const isSample = agent.source_kind === 'sample'
  const canLaunch = !isSample && !!agent.access.launch_url
  // The header's action column is shown only when there is something to do.
  // Open agents without a live link still get the column, to say the link is coming.
  const hasAction = access === 'open' || access === 'request' || access === 'restricted'
  const ownerMail = agent.owner.email
    ? `mailto:${agent.owner.email}?subject=${encodeURIComponent(`Access to ${agent.name}`)}`
    : undefined

  // One click to act. The hero's Request access button brings the Get access
  // card into view and puts the cursor in the reason box, so the request is
  // typed straight away rather than scrolled to and then clicked into.
  function goToRequest(e: React.MouseEvent) {
    const card = document.getElementById('request-access')
    if (!card) return
    e.preventDefault()
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    card.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    card.querySelector<HTMLTextAreaElement>('textarea')?.focus({ preventScroll: true })
  }

  return (
    <div className="content agent">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <Link to="/marketplace">AI Marketplace</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <span>{agent.name}</span>
      </nav>

      <div className="doc__bar">
        <BackButton fallback="/marketplace" label="Back to marketplace" />
      </div>

      {/* The first screen holds the whole decision: what it is, who it is for,
          who owns it, and every action -- each one click from here. It used to
          take two and a half screens of cards and a sidebar to learn the same. */}
      <header className="agent__head">
        <div className="agent__head-top">
          <div className="agent__head-main">
            <div className="agent__badges">
              <span className={`status status--${agent.status}`}>{STATUS_LABEL[agent.status]}</span>
              <span className="agent__category">{agent.category}</span>
              {agent.version && <span className="agent__version">v{agent.version}</span>}
              {forYou && <span className="acard__foryou">For your persona</span>}
            </div>
            <h1 className="agent__name">{agent.name}</h1>
            <p className="agent__tagline">{agent.tagline}</p>
          </div>

          {/* An empty action column kept a third of the header blank. */}
          {hasAction && (
            <div className="agent__actions">
              {/* Where launching is the action but no link is live yet, say so where the button will be. */}
              {access === 'open' && !canLaunch && (
                <p className="agent__pending">
                  <Clock size={14} strokeWidth={2.2} aria-hidden="true" /> Launch link coming soon
                </p>
              )}
              {access === 'open' && canLaunch && (
                <ExtLink href={agent.access.launch_url} event="launch" agent={agent} className="btn btn--inline">
                  <Rocket size={18} /> Launch agent
                </ExtLink>
              )}

              {access === 'request' && (
                <>
                  <a className="btn btn--inline" href="#request-access" onClick={goToRequest}>
                    Request access
                  </a>
                  {!isSample && agent.access.request_url && (
                    <ExtLink href={agent.access.request_url} event="request_access" agent={agent} className="btn-outline">
                      Open enterprise access portal
                    </ExtLink>
                  )}
                </>
              )}

              {access === 'restricted' && (
                <a className="btn-outline" href={ownerMail} aria-disabled={!ownerMail}>
                  Contact the owner for access
                </a>
              )}
            </div>
          )}
        </div>

        {/* The facts a reader checks before opening it, in one row under the name. */}
        <dl className="agent__facts">
          <div>
            <dt>Used by</dt>
            <dd>{agent.personas.map((p) => PERSONA_LABEL[p] ?? p).join(', ') || <Unconfirmed />}</dd>
          </div>
          <div>
            <dt>Domains</dt>
            <dd>{agent.business_domains.join(', ') || <Unconfirmed />}</dd>
          </div>
          <div>
            <dt>Owner</dt>
            {/* A first-pass listing may not have a named owner yet: the team is
                shown, and the person says it is to be confirmed. */}
            <dd>
              {agent.owner.team || <Unconfirmed />}
              <span className="agent__fact-sub">{agent.owner.name || <Unconfirmed text="Contact to be confirmed" />}</span>
            </dd>
          </div>
          <div>
            <dt>Platform</dt>
            <dd>{agent.platform || <Unconfirmed />}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{formatDate(agent.updated_at)}</dd>
          </div>
        </dl>
      </header>

      <div className="agent__body">
        <div className="agent__overview">
          {/* What it does and why it was built are read together, so they sit together. */}
          <section className="panel">
            <h2 className="panel__title">What it does</h2>
            <p className="panel__text">{agent.description}</p>
            {agent.problem_solved && (
              <>
                <h3 className="panel__subtitle">Why it exists</h3>
                <p className="panel__text">{agent.problem_solved}</p>
              </>
            )}
          </section>

          <section className="panel">
            <h2 className="panel__title">What you can ask it to do</h2>
            <ul className="usecases">
              {(agent.use_cases ?? []).map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
            {(agent.example_tasks?.length ?? 0) > 0 && (
              <div className="examples-inline">
                <span className="examples__label">Example prompts</span>
                {agent.example_tasks.map((t) => (
                  <span key={t} className="examples__chip examples__chip--static">
                    {t}
                  </span>
                ))}
              </div>
            )}
            <h3 className="panel__subtitle">Capabilities</h3>
            <div className="pills">
              {(agent.capabilities ?? []).map((c) => (
                <span key={c} className="pill">
                  {c}
                </span>
              ))}
            </div>
          </section>
        </div>

        {/* Documents stay where the owning team keeps them: Nexus lists each
            with what it covers and a link to open it there, and holds no copy. */}
        <section className="panel" id="documents">
          <h2 className="panel__title">
            <FileText size={20} strokeWidth={2.4} /> Documentation
          </h2>
          <p className="panel__text">
            Each document stays where the owning team keeps it. Open a link to read it there.
          </p>
          {sources === undefined && <div className="skeleton" style={{ height: 96 }} />}
          {sources === null && <p className="muted">The document list could not load. Try again in a moment.</p>}
          {sources && (
            <div className="ks-table-wrap">
              <table className="ks-table">
                <thead>
                  <tr>
                    <th scope="col">Document</th>
                    <th scope="col">What it covers</th>
                    <th scope="col">Open it</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.document_types.map((type) => {
                    const doc = agent.documents.find((d) => d.type === type.id)
                    const system = sources.systems.find((s) => s.id === doc?.system)
                    const covers = doc?.description || type.about
                    return (
                      <tr key={type.id}>
                        <th scope="row">
                          <span className="ks-abbr">{type.abbreviation}</span>
                          <span className="ks-name">{type.name || <span className="tbc">To be confirmed</span>}</span>
                        </th>
                        <td data-label="What it covers">{covers || <span className="tbc">To be confirmed</span>}</td>
                        {/* Where it lives and the link read as one thing: one cell, not
                            two that both said "To be confirmed". */}
                        <td data-label="Open it">
                          {doc?.url ? (
                            <ExtLink
                              href={doc.url}
                              event={type.id === 'hld' || type.id === 'lld' ? 'architecture_click' : 'documentation_click'}
                              agent={agent}
                              className="linkbtn"
                            >
                              <ExternalLink size={14} strokeWidth={2.2} />{' '}
                              {system ? `Open in ${system.name}` : `Open ${type.abbreviation}`}
                            </ExtLink>
                          ) : (
                            <span className="tbc">
                              {system ? `In ${system.name}, link to be confirmed` : 'Link to be confirmed'}
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* How to get it, and who owns it: two plain halves of one card. */}
        <section className="panel access" id="request-access">
          <div className="access__route">
            <h2 className="panel__title">
              <ShieldCheck size={20} strokeWidth={2.4} /> Get access
            </h2>
            <span className={`access__type access__type--${access}`}>{ACCESS_LABEL[agent.access.type]}</span>
            <p className="panel__text">{agent.access.how}</p>
            {/* A request form only makes sense where a request is the route in.
                Open agents need none; restricted ones go through the owner. */}
            {access === 'request' && <AccessRequestForm key={agent.id} agentId={agent.id} />}
          </div>
          <div className="access__owner">
            <h3 className="access__label">Owner</h3>
            <div className="access__person">
              <span className="access__avatar" aria-hidden="true">
                {initials(agent.owner.name || agent.owner.team)}
              </span>
              <div>
                <p className="access__name">{agent.owner.name || 'To be confirmed'}</p>
                <p className="access__team">{agent.owner.team}</p>
              </div>
            </div>
            {agent.source_kind === 'enterprise' && agent.owner.email ? (
              <a
                className="btn-outline access__contact"
                href={`mailto:${agent.owner.email}?subject=${encodeURIComponent(agent.name)}`}
                onClick={() => track('marketplace', 'collaborate', { subject_id: agent.id })}
              >
                <MessageSquare size={16} strokeWidth={2.4} /> Contact the owner
              </a>
            ) : (
              <p className="access__pending">Contact details appear once the owning team confirms this listing.</p>
            )}
          </div>
        </section>

        {related.length > 0 && (
          <section>
            <h2 className="section-title">Related agents</h2>
            <div className="agent-grid">
              {related.map((a) => (
                <AgentCard key={a.id} agent={a} source="related" compact />
              ))}
            </div>
          </section>
        )}

        {/* Learning comes last: the agent first, then what helps you use it. */}
        {(videos?.length ?? 0) > 0 && (
          <section className="panel">
            <div className="section-head section-head--tight">
              <div>
                <h2 className="panel__title" style={{ margin: 0 }}>
                  Learning for this agent
                </h2>
                <p className="section-sub">
                  Related material selected by Learning. Use your account's Learning page for progress and required steps.
                </p>
              </div>
              <Link to="/learning" className="textlink">
                All learning
              </Link>
            </div>
            <div className="video-row">
              {videos.map((v) => (
                <ItemCard key={v.id} item={v} fromAgentId={agent.id} compact />
              ))}
            </div>
          </section>
        )}

        <FeedbackPrompt pillar="marketplace" context="agent" subjectId={agent.id} resetKey={agent.id} question="Was this page useful?" />
      </div>
    </div>
  )
}
