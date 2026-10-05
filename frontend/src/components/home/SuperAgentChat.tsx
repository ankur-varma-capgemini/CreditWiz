import {
  FileText,
  GraduationCap,
  Landmark,
  Network,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { addTurn, finishTurn, rateTurn, startChat, updateTurn, useChats } from '../../lib/chats'
import { track } from '../../lib/context'
import { askHubStream, reduceLive, startLive } from '../../lib/journeys'
import { AssistantAnswer } from './AssistantAnswer'
import { Composer } from './Composer'
import { ConversationSwitcher, RecentConversations } from './Conversations'
import { HubMark } from './HubMark'

// What each suggested request is about, at a glance.
const TOPIC_ICONS: [RegExp, LucideIcon][] = [
  [/sanction|screen/i, ShieldCheck],
  [/\bown|beneficial|ubo\b/i, Network],
  [/contract|summar|document/i, FileText],
  [/fatca|w-8|tax|classif/i, Landmark],
  [/course|learn|training/i, GraduationCap],
  [/who can|expert/i, Users],
]

function topicIcon(text: string): LucideIcon {
  return TOPIC_ICONS.find(([pattern]) => pattern.test(text))?.[1] ?? Sparkles
}

interface Props {
  /** Whose conversations: each account keeps its own, in this browser. */
  userId: string
  firstName: string
  initials: string
  persona: string
  personaLabel: string
  examples: string[]
}

/**
 * The Super Agent: one conversation across every pillar. Before the first
 * question: the composer, suggestions and recent conversations. After it: a
 * transcript filling the screen, with the composer resting at its foot. Each
 * reply comes from /api/ask, the hub's graph: the job, what every pillar
 * found, and how it was chosen.
 *
 * Every conversation is kept (lib/chats). The latest are listed under the
 * composer, and a conversation's title opens all of them; ?chat= says which
 * one is open, ?q= starts a new one with that question (home's ask bar).
 */
export function SuperAgentChat({ userId, firstName, initials, persona, personaLabel, examples }: Props) {
  const [params, setParams] = useSearchParams()
  const chatId = params.get('chat') ?? ''
  const chat = useChats(userId).find((c) => c.id === chatId)
  const turns = chat?.turns ?? []
  const [draft, setDraft] = useState('')
  const log = useRef<HTMLDivElement>(null)
  const started = useRef(false)
  const nextId = useRef(0)
  const busy = turns.some((t) => t.status === 'loading')
  const talking = turns.length > 0

  // A conversation this browser doesn't hold (deleted, or kept in another
  // browser) leaves home on a new one rather than an empty transcript.
  useEffect(() => {
    if (chatId && !chat) setParams({}, { replace: true })
  }, [chatId, chat, setParams])

  // Bring the latest question to the top of the view, just under the top bar
  // and the conversation's header, so its answer reads from the start rather
  // than from the foot of a long list. The page scrolls, not the transcript.
  const count = turns.length
  useEffect(() => {
    const asked = log.current?.querySelectorAll<HTMLElement>('.msg--me')
    const last = asked?.[asked.length - 1]
    if (!last) return
    const above = ['.topbar', '.chat__bar'].reduce((h, s) => h + (document.querySelector<HTMLElement>(s)?.offsetHeight ?? 0), 0)
    window.scrollTo({ top: window.scrollY + last.getBoundingClientRect().top - above - 12, behavior: 'smooth' })
  }, [count, chatId])

  async function send(text: string) {
    const q = text.trim()
    if (!q || busy) return
    const current = chat ?? startChat(userId)
    if (!chat) setParams({ chat: current.id }, { replace: true })
    const id = Date.now() + ++nextId.current
    // A follow-up that names no job or client stays on the ones the
    // conversation was on, which it carries itself.
    const earlier = [...current.turns].reverse()
    const journey = earlier.find((t) => t.ask?.task?.activity)?.ask?.task?.activity?.id
    const subject = earlier.find((t) => t.ask?.task?.subject)?.ask?.task?.subject?.name
    // And its earlier requests, so "is there one for it?" is read as about them.
    const history = current.turns
      .filter((t) => t.status === 'done' && t.ask?.kind === 'task')
      .map((t) => t.q)
      .slice(-6)
    setDraft('')
    addTurn(userId, current.id, { id, q, status: 'loading', live: startLive() })
    // The answer builds event by event, in its own conversation, even if
    // another one is opened while it arrives.
    try {
      const ask = await askHubStream(q, persona, { journey, subject, session: current.session_id, history }, (e) =>
        updateTurn(userId, current.id, id, (t) => (t.live ? { ...t, live: reduceLive(t.live, e) } : t)),
      )
      finishTurn(userId, current.id, id, ask)
      // Usage analytics get the server's loggable form: a client name never,
      // and for small talk only what kind it was.
      track('hub', 'search', {
        query: ask.task ? ask.task.loggable_query : `[${ask.kind}]`,
        persona,
        meta: ask.task
          ? {
              surface: 'chat',
              intents: ask.task.intents,
              journey: ask.task.activity?.id ?? null,
              pillars: ask.plan?.selected_pillars ?? [],
              sensitivity: ask.task.sensitivity,
              planned_by: ask.plan?.plan_source ?? null,
            }
          : { surface: 'chat', kind: ask.kind },
      })
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : 'The hub could not answer just now.'
      updateTurn(userId, current.id, id, (t) => ({ ...t, status: 'error', error, live: undefined }))
    }
  }

  function rated(id: number, helpful: boolean) {
    if (chat) rateTurn(userId, chat.id, id, helpful)
  }

  // A link to /?q=... still opens a new conversation with that question.
  useEffect(() => {
    const q = params.get('q')
    if (started.current || !q) return
    started.current = true
    void send(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The conversation is kept, among the recent ones; home goes back to a new one.
  function startNew() {
    setDraft('')
    setParams({})
  }

  return (
    <div className={`content home${talking ? ' home--talking' : ''}`}>
      <section className={`chat${talking ? ' is-talking' : ''}`} aria-label="Super Agent">
        {talking && chat ? (
          <div className="chat__bar">
            <ConversationSwitcher userId={userId} chat={chat} />
            <button type="button" className="chat__new" onClick={startNew}>
              <SquarePen size={15} strokeWidth={2.2} aria-hidden="true" /> New conversation
            </button>
          </div>
        ) : (
          <>
            <p className="chat__kicker">
              <HubMark /> Super Agent
            </p>
            <h1 className="chat__title">How can I help, {firstName}?</h1>
            <p className="chat__sub">One request, every pillar: the agents, prompts, learning and experts for your task.</p>
          </>
        )}

        {talking && (
          <div className="chatlog" ref={log} aria-live="polite">
            {turns.map((t, i) => (
              <Fragment key={t.id}>
                <div className="msg msg--me">
                  <span className="msg__who" aria-hidden="true">
                    {initials}
                  </span>
                  <div className="bubble">{t.q}</div>
                </div>
                <div className="msg msg--ai">
                  <span className="msg__who msg__who--hub" aria-hidden="true">
                    <HubMark />
                  </span>
                  <div className="bubble">
                    <AssistantAnswer turn={t} latest={i === turns.length - 1} onAsk={send} onRated={rated} />
                  </div>
                </div>
              </Fragment>
            ))}
          </div>
        )}

        <div className={talking ? 'dock' : undefined}>
          <Composer
            value={draft}
            onChange={setDraft}
            onSend={send}
            busy={busy}
            personaLabel={personaLabel}
            placeholder="Describe the task you need help with"
            autoFocus={talking}
          />
          {!talking && (
            <div className="suggests suggests--start" role="group" aria-label="Try asking">
              {examples.map((q) => {
                const Icon = topicIcon(q)
                return (
                  <button key={q} type="button" className="suggest suggest--start" onClick={() => send(q)}>
                    <span className="suggest__icon">
                      <Icon size={16} strokeWidth={2} aria-hidden="true" />
                    </span>
                    {q}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {!talking && <RecentConversations userId={userId} />}
      </section>
    </div>
  )
}
