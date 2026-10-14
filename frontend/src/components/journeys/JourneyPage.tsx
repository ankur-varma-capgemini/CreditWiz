import { ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, isAbort } from '../../lib/api'
import { track } from '../../lib/context'
import {
  fetchJourney,
  INTENT_HINT,
  INTENT_LABEL,
  INTENTS,
  type Intent,
  type JourneyPage as Journey,
} from '../../lib/journeys'
import { usePersona } from '../../lib/personaContext'
import '../../journeys.css'
import { FeedbackPrompt } from '../marketplace/FeedbackPrompt'
import { PageBand } from '../PageBand'
import { NotFound } from '../SimplePages'
import { AssetList } from './AssetList'

/**
 * One job, end to end: what helps, grouped by why someone came (find, learn,
 * improve, ask, contribute), how the work runs, and which systems do it. The
 * hub guides and opens; the systems of record keep the data and do the work.
 */
export function JourneyPage() {
  const { id = '' } = useParams()
  const { persona } = usePersona()
  const [params] = useSearchParams()
  const picked = params.get('intent') as Intent | null
  const [journey, setJourney] = useState<Journey | null | undefined>(undefined)
  const [error, setError] = useState('')

  useEffect(() => {
    const ctrl = new AbortController()
    setJourney(undefined)
    fetchJourney(id, persona, ctrl.signal)
      .then((j) => {
        setError('')
        setJourney(j)
        track('hub', 'view', { subject_id: j.id, subject_type: 'journey', persona })
      })
      .catch((e: unknown) => {
        if (isAbort(e)) return
        if (e instanceof ApiError && e.status === 404) setJourney(null)
        else setError(e instanceof Error ? e.message : 'Could not load this journey')
      })
    return () => ctrl.abort()
  }, [id, persona])

  if (error)
    return (
      <div className="content" role="alert">
        {error}
      </div>
    )
  if (journey === null) return <NotFound />
  if (journey === undefined)
    return (
      <div className="content">
        <div className="skeleton" style={{ height: 180, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    )

  const present = INTENTS.filter((i) => journey.assets.some((a) => a.intent === i))
  const intent = picked && present.includes(picked) ? picked : null
  const groups = intent ? [intent] : present

  return (
    <div className="content journey">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <Link to="/journeys">Your work</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <span>{journey.title}</span>
      </nav>

      <PageBand compact kicker={`${journey.persona_label} · Your work`} title={journey.title} lead={journey.summary}>
        <nav className="pathbar pathbar--onband" aria-label="What you are here to do">
          <Link className={`pathbar__item${intent ? '' : ' is-active'}`} to={{ search: '' }} replace>
            Everything
          </Link>
          {present.map((i) => (
            <Link
              key={i}
              className={`pathbar__item${intent === i ? ' is-active' : ''}`}
              to={{ search: `?intent=${i}` }}
              replace
            >
              {INTENT_LABEL[i]}
            </Link>
          ))}
        </nav>
      </PageBand>

      <div className="journey__grid">
        <div className="journey__main">
          {groups.map((i) => (
            <section key={i} className="panel journey__group" aria-labelledby={`group-${i}`}>
              <div className="journey__group-head">
                <h2 className="journey__group-title" id={`group-${i}`}>
                  {INTENT_LABEL[i]}
                </h2>
                <span className="journey__hint">{INTENT_HINT[i]}</span>
              </div>
              <AssetList assets={journey.assets.filter((a) => a.intent === i)} journeyId={journey.id} />
            </section>
          ))}
          {groups.includes('contribute') && (
            <p className="journey__note">
              <strong>How contributions are reviewed</strong>
              Share a prompt, a use case or a correction. It is reviewed through MUFG&rsquo;s existing workflow tool, not
              inside Nexus. Which tool is to be confirmed.
            </p>
          )}
        </div>

        <aside className="journey__side">
          <section className="panel">
            <h2 className="panel__title">How the work gets done</h2>
            <ol className="jsteps">
              {journey.steps.map((s) => (
                <li key={s.title}>
                  <div>
                    <strong>{s.title}</strong>
                    <p>{s.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="panel">
            <h2 className="panel__title">Who does what</h2>
            <div className="roles">
              <div>
                <h3>Nexus</h3>
                <p>
                  Finds what fits the job, shows whether you can trust it, opens it in the right place and learns from your
                  feedback. It holds no client data.
                </p>
              </div>
              <div>
                <h3>Systems of record</h3>
                <ul>
                  {journey.systems.map((s) => (
                    <li key={s.system}>
                      <strong>{s.system}</strong> {s.does}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>

          <FeedbackPrompt
            pillar="hub"
            context="journey"
            subjectId={journey.id}
            resetKey={journey.id}
            question="Did this journey have what you needed?"
          />
        </aside>
      </div>
    </div>
  )
}
