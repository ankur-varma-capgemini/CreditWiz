import { ArrowRight, ArrowUp, Bell, MessagesSquare } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchNotifications, isAbort } from '../lib/api'
import { useChats } from '../lib/chats'
import { useHub } from '../lib/hub'
import { fetchJourneys, type JourneysHome } from '../lib/journeys'
import { fetchMarketplaceHome, type Agent } from '../lib/marketplace'
import { usePersona } from '../lib/personaContext'
import type { Notification } from '../lib/types'
import '../home.css'
import '../journeys.css'
import { ForYou } from './home/ForYou'
import { HubMark } from './home/HubMark'
import { JourneyGrid } from './journeys/JourneyGrid'

function timeAgo(iso: string): string {
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000)
  if (h < 1) return 'just now'
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return d === 1 ? 'yesterday' : `${d}d ago`
}

/** "Good morning" before noon, "Good afternoon" before six, then "Good evening". */
function greeting(hour = new Date().getHours()) {
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}

/**
 * A question typed on home goes straight to the Super Agent, already asked:
 * the conversation happens there, on its own page, and home stays home.
 */
function AskBar({ conversations }: { conversations: number }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  function ask(e: FormEvent) {
    e.preventDefault()
    const text = q.trim()
    if (text) navigate(`/super-agent?q=${encodeURIComponent(text)}`)
  }
  return (
    <div className="askbar-wrap">
      <form className="askbar" role="search" aria-label="Ask the Super Agent" onSubmit={ask}>
        <span className="askbar__mark">
          <HubMark size={18} />
        </span>
        <input
          className="askbar__input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask the Super Agent about a task"
          aria-label="Ask the Super Agent"
          maxLength={500}
        />
        <button type="submit" className="askbar__go" disabled={!q.trim()} aria-label="Ask">
          <span className="askbar__go-label">Ask</span>
          <ArrowUp size={15} strokeWidth={2.4} aria-hidden="true" />
        </button>
      </form>
      <Link to="/super-agent" className="askbar__link">
        <MessagesSquare size={14} strokeWidth={2.2} aria-hidden="true" />
        {conversations ? `Your conversations (${conversations})` : 'Open the Super Agent'}
        <ArrowRight size={14} strokeWidth={2.4} aria-hidden="true" />
      </Link>
    </div>
  )
}

/**
 * Home: the person's own front page. What to pick up next, their work, the
 * agents picked for them and what is new. The Super Agent has a page of its
 * own, below Home in the sidebar; a question asked here opens there.
 */
export function HomePage() {
  const data = useHub()
  const { persona } = usePersona()
  const conversations = useChats(data.user.id).length
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

  return (
    <div className="content home">
      <section className="dash-hero" aria-labelledby="dash-title">
        <h1 className="dash-hero__title" id="dash-title">
          {greeting()}, {data.user.first_name}
        </h1>
        <p className="dash-hero__sub">Your work, your learning and your communities, in one place.</p>
        <AskBar conversations={conversations} />
      </section>
      {below}
    </div>
  )
}
