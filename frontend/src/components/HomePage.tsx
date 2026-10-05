import { ArrowRight, Bell } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchNotifications, isAbort } from '../lib/api'
import { useHub } from '../lib/hub'
import { fetchJourneys, type JourneysHome } from '../lib/journeys'
import { fetchMarketplaceHome, type Agent } from '../lib/marketplace'
import { usePersona } from '../lib/personaContext'
import type { Notification } from '../lib/types'
import '../home.css'
import '../journeys.css'
import { ForYou } from './home/ForYou'
import { HomeChat } from './home/HomeChat'
import { JourneyGrid } from './journeys/JourneyGrid'

function timeAgo(iso: string): string {
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000)
  if (h < 1) return 'just now'
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return d === 1 ? 'yesterday' : `${d}d ago`
}

/**
 * Home is the hub's front door, not the marketplace's: one conversation that
 * takes any request. It is where the hub's router agent (LangGraph, each
 * pillar an agent) plugs in later; today /api/ask reads the intent and the job,
 * and the hub search answers the rest.
 */
const EXAMPLES = [
  'Screen a client against sanctions lists',
  'Who ultimately owns a company',
  'Summarise a contract',
  'Check W-8 and FATCA classification',
]

export function HomePage() {
  const data = useHub()
  const { persona } = usePersona()
  const [work, setWork] = useState<JourneysHome | null>(null)
  const [picked, setPicked] = useState<Agent[] | null>(null)
  const [error, setError] = useState('')
  const [news, setNews] = useState<Notification[]>([])

  useEffect(() => {
    const ctrl = new AbortController()
    fetchMarketplaceHome(persona, ctrl.signal, 'all')
      .then((h) => {
        setError('')
        setPicked((h.carousels.find((c) => c.id === 'recommended')?.agents ?? []).slice(0, 3))
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Could not load agents')
      })
    fetchJourneys(persona, ctrl.signal)
      .then(setWork)
      .catch((e: unknown) => {
        if (!isAbort(e)) setWork(null)
      })
    fetchNotifications(ctrl.signal)
      .then((n) => setNews(n.slice(0, 3)))
      .catch((err: unknown) => {
        if (!isAbort(err)) setNews([])
      })
    return () => ctrl.abort()
  }, [persona])

  const below = (
    <>
      <ForYou persona={persona} />

      {work && work.journeys.length > 0 && (
        <section className="home-work" aria-labelledby="home-work-title">
          <div className="home-work__head">
            <h2 className="home-work__title" id="home-work-title">
              Your work
            </h2>
            <p className="home-work__lead">The jobs you do as a {work.persona_label}, and what helps at each one.</p>
          </div>
          <JourneyGrid journeys={work.journeys} />
        </section>
      )}

      <div className="home-cards">
        <section className="panel home-card" aria-labelledby="home-picked">
          <div className="home-card__head">
            <h2 className="home-card__title" id="home-picked">
              Picked for you
            </h2>
            <Link to="/marketplace" className="textlink">
              All agents <ArrowRight size={14} strokeWidth={2.4} />
            </Link>
          </div>
          {error ? (
            <p role="alert">{error}</p>
          ) : picked ? (
            <ul className="home-list">
              {picked.map((a) => (
                <li key={a.id}>
                  <Link className="home-row" to={`/marketplace/agents/${a.id}`}>
                    <span className="home-row__title">{a.name}</span>
                    <span className="home-row__sub">{a.tagline}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="skeleton" style={{ height: 150 }} />
          )}
        </section>

        <section className="panel home-card" aria-labelledby="home-jump">
          <div className="home-card__head">
            <h2 className="home-card__title" id="home-jump">
              Jump back in
            </h2>
          </div>
          <ul className="home-list">
            <li>
              <Link className="home-row" to="/learning/me">
                <span className="home-row__title">My learning</span>
                <span className="home-row__sub">Progress, required steps and saved items.</span>
              </Link>
            </li>
            <li>
              <Link className="home-row" to="/learning/catalog">
                <span className="home-row__title">Learning catalog</span>
                <span className="home-row__sub">Videos, runbooks and quick references.</span>
              </Link>
            </li>
            <li>
              <Link className="home-row" to="/community">
                <span className="home-row__title">Community</span>
                <span className="home-row__sub">Forums, SME directory and FAQs.</span>
              </Link>
            </li>
          </ul>
        </section>

        <section className="panel home-card" aria-labelledby="home-news">
          <div className="home-card__head">
            <h2 className="home-card__title" id="home-news">
              <Bell size={16} strokeWidth={2.4} /> What's new
            </h2>
          </div>
          {news.length === 0 ? (
            <p className="muted">Nothing new right now.</p>
          ) : (
            <ul className="home-list">
              {news.map((n) => (
                <li key={n.id}>
                  <Link className="home-row" to={n.href}>
                    <span className="home-row__title">{n.title}</span>
                    <span className="home-row__sub">{n.body}</span>
                    <span className="home-row__time">{timeAgo(n.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  )

  // Keyed by user and persona, so a persona preview starts its own conversation.
  const key = `mufg.home-chat.${data.user.id}.${persona}`
  return (
    <HomeChat
      key={key}
      storeKey={key}
      firstName={data.user.first_name}
      initials={data.user.initials}
      persona={persona}
      personaLabel={work?.persona_label ?? data.user.persona.label}
      examples={work?.examples.length ? work.examples : EXAMPLES}
      below={below}
    />
  )
}
