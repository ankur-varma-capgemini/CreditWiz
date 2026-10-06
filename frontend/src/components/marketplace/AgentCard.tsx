import { ArrowRight, Lock, Unlock, UserCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { track } from '../../lib/context'
import { STATUS_LABEL, type Agent } from '../../lib/marketplace'
import { usePersona } from '../../lib/personaContext'
import { subjectIcon } from '../../lib/visuals'
import { Cover } from '../Cover'

interface Props {
  agent: Agent
  why?: string
  reasons?: string[]
  source: string
  compact?: boolean
  /** The whole row is already persona-ranked, so the per-card badge is noise. */
  hideForYou?: boolean
}

function AccessIcon({ type }: { type: Agent['access']['type'] }) {
  if (type === 'open') return <Unlock size={14} strokeWidth={2.4} />
  if (type === 'request') return <UserCheck size={14} strokeWidth={2.4} />
  return <Lock size={14} strokeWidth={2.4} />
}

export function AgentCard({ agent, why, reasons, source, compact, hideForYou }: Props) {
  const { persona } = usePersona()
  const forYou = !hideForYou && agent.personas.includes(persona)
  const domain = agent.business_domains[0] ?? ''
  return (
    <Link
      to={`/marketplace/agents/${agent.id}`}
      className={`acard${compact ? ' acard--compact' : ''}`}
      onClick={() =>
        track('marketplace', 'click', {
          subject_id: agent.id,
          subject_type: 'agent',
          persona,
          topics: [...agent.business_domains, ...agent.capabilities],
          meta: { source },
        })
      }
    >
      <div className="card-head">
        <Cover icon={subjectIcon(domain)} size="tile" />
        <div className="acard__top">
          <span className="acard__kicker">
            {domain}
            <span className="acard__dot">•</span>
            <span className={`status status--${agent.status}`}>{STATUS_LABEL[agent.status]}</span>
          </span>
          {forYou && (
            <span className="acard__foryou" title="Built for your persona">
              For you
            </span>
          )}
        </div>
      </div>
      <h3 className="acard__name">{agent.name}</h3>
      <p className="acard__tagline">{agent.tagline}</p>
      {agent.capabilities.length > 0 && (
        <div className="acard__caps">
          {agent.capabilities.slice(0, compact ? 2 : 3).map((c) => (
            <span key={c} className="acard__cap">
              {c}
            </span>
          ))}
        </div>
      )}
      {why && <p className="acard__why">{why}</p>}
      {reasons && reasons.length > 0 && (
        <ul className="acard__reasons">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <div className="acard__meta">
        <span className="acard__domains">{agent.owner.team}</span>
        <span className={`acard__access acard__access--${agent.access.type}`}>
          <AccessIcon type={agent.access.type} />
          {agent.access.type === 'open' ? 'Open' : agent.access.type === 'request' ? 'Request' : 'Restricted'}
        </span>
      </div>
      <span className="acard__go">
        View agent <ArrowRight size={16} strokeWidth={2.4} />
      </span>
    </Link>
  )
}
