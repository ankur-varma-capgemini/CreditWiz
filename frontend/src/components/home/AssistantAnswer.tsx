import {
  ArrowRight,
  Bot,
  Briefcase,
  Check,
  ChevronRight,
  Copy,
  CornerDownRight,
  GraduationCap,
  Info,
  Layers,
  Loader2,
  Lock,
  MessageSquareText,
  PenLine,
  Plus,
  RotateCcw,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  UserRound,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { track, type Maturity, type UserContext } from '../../lib/context'
import { useCreate } from '../../lib/create'
import { useHub } from '../../lib/hub'
import { matchSections } from '../../lib/hubSearch'
import {
  INTENT_LABEL,
  PILLAR_LABEL,
  SENSITIVITY_LABEL,
  openedFromTurn,
  rateTurn,
  type AskResponse,
  type Live,
  type PillarGroup,
  type PillarHit,
  type PillarName,
  type Plan,
  type TaskContext,
} from '../../lib/journeys'
import { draftPrompt, type Draft } from '../../lib/prompts'
import { AssetList } from '../journeys/AssetList'

export interface Turn {
  id: number
  q: string
  status: 'loading' | 'done' | 'error'
  /** What has arrived so far, while the answer streams in. */
  live?: Live
  ask?: AskResponse
  error?: string
  /** What they said about the answer, once they have. */
  helpful?: boolean
}

const SHOWN = 3
const RECOMMENDED = 4

/** 17 ms, 2.8 s */
function duration(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`
}

const MATURITY_LABEL: Record<Maturity, string> = {
  beginner: 'Beginner',
  developing: 'Developing',
  experienced: 'Experienced',
}

const PILLAR_ICON: Record<PillarName, LucideIcon> = {
  prompts: MessageSquareText,
  marketplace: Bot,
  learning: GraduationCap,
  community: Users,
}

const BROWSE: Record<PillarName, string> = {
  prompts: 'Open the library',
  marketplace: 'See all in Discover',
  learning: 'Catalog',
  community: 'Open Community',
}

const HIT_ICON: Record<string, LucideIcon> = {
  prompt: MessageSquareText,
  agent: Bot,
  learning: GraduationCap,
  expert: UserRound,
  community: Users,
  page: Layers,
}

const MODEL_ACCESS: Record<Plan['model_access'], string> = {
  as_typed: 'The data policy let the approved model receive it as typed.',
  masked: 'The data policy let the model receive it with client details masked.',
  none: 'The data policy let no model receive it.',
}

function Group({
  icon: Icon,
  title,
  count,
  link,
  children,
}: {
  icon: LucideIcon
  title: string
  count: number
  link?: { to: string; label: string }
  children: ReactNode
}) {
  return (
    <section className="aigroup">
      <div className="aihead">
        <Icon size={16} strokeWidth={2.2} aria-hidden="true" />
        <b>{title}</b>
        <span className="aicount">{count}</span>
        {link && (
          <Link className="ailink" to={link.to}>
            {link.label} <ArrowRight size={13} strokeWidth={2.4} />
          </Link>
        )}
      </div>
      {children}
    </section>
  )
}

function HitRow({ hit, onOpen }: { hit: PillarHit; onOpen?: () => void }) {
  const Icon = HIT_ICON[hit.kind] ?? Layers
  const body = (
    <>
      <span className="airow__icon" aria-hidden="true">
        <Icon size={18} strokeWidth={2.2} />
      </span>
      <span className="airow__body">
        <span className="airow__title">
          {hit.title}
          {hit.fit === 'partial' && (
            <span className="fitchip" title="The agent judged it the closest thing, or a fit for part of what you asked">
              Partial match
            </span>
          )}
        </span>
        <span className="airow__sub">{hit.meta || hit.summary}</span>
      </span>
    </>
  )
  return (
    <li>
      {!hit.href ? (
        <div className="airow airow--static">
          {body}
          <span className="airow__pending">Link to be confirmed</span>
        </div>
      ) : hit.href.startsWith('/') ? (
        <Link className="airow" to={hit.href} onClick={onOpen}>
          {body}
          <ChevronRight className="airow__go" size={16} strokeWidth={2.2} aria-hidden="true" />
        </Link>
      ) : (
        <a className="airow" href={hit.href} target="_blank" rel="noreferrer" onClick={onOpen}>
          {body}
          <ChevronRight className="airow__go" size={16} strokeWidth={2.2} aria-hidden="true" />
        </a>
      )}
    </li>
  )
}

function PillarGroupView({ group, onOpen }: { group: PillarGroup; onOpen?: (hit: PillarHit) => void }) {
  return (
    <Group
      icon={PILLAR_ICON[group.pillar]}
      title={group.label}
      count={group.hits.length}
      link={{
        // The pillar's own query: the request with client details removed.
        to: group.pillar === 'marketplace' ? `/marketplace?q=${encodeURIComponent(group.query)}` : group.href,
        label: BROWSE[group.pillar],
      }}
    >
      <ul className="airows">
        {group.hits.map((h) => (
          <HitRow key={h.ref} hit={h} onOpen={onOpen && (() => onOpen(h))} />
        ))}
      </ul>
    </Group>
  )
}

function ContextChips({ task, followsOn = '' }: { task: TaskContext; followsOn?: string }) {
  if (!followsOn && !task.subject && task.sensitivity === 'internal') return null
  return (
    <p className="answer__context">
      {/* A follow-up read with the conversation's earlier topic says which. */}
      {followsOn && (
        <span className="ctxchip" title="Read with what you asked earlier in this conversation">
          <CornerDownRight size={13} strokeWidth={2.2} aria-hidden="true" />
          Following on: <b>{followsOn}</b>
        </span>
      )}
      {task.subject && (
        <span className="ctxchip">
          <Briefcase size={13} strokeWidth={2.2} aria-hidden="true" />
          {task.activity?.id === 'meeting-prep' ? 'Preparing for' : 'About'}: <b>{task.subject.name}</b>
        </span>
      )}
      {task.sensitivity !== 'internal' && (
        <span className="ctxchip ctxchip--sensitive" title={task.sensitivity_reason}>
          <Lock size={13} strokeWidth={2.2} aria-hidden="true" />
          {SENSITIVITY_LABEL[task.sensitivity]}
        </span>
      )}
    </p>
  )
}

/** A prompt written from the validated ones. Nothing is saved until contributed. */
function DraftCard({ draft, busy, onAnother }: { draft: Draft; busy: boolean; onAnother: () => void }) {
  const { open } = useCreate()
  const [copied, setCopied] = useState(false)
  return (
    <section className="draftcard" aria-label={`Draft prompt: ${draft.title}`}>
      <div className="draftcard__head">
        <PenLine size={18} strokeWidth={2.2} aria-hidden="true" />
        <div>
          <b>Draft prompt · {draft.title}</b>
          <span className="muted">Written for you from validated prompts. Nothing is saved until you contribute it.</span>
        </div>
      </div>
      <pre className="codeblock codeblock--compact">{draft.body}</pre>
      <p className="draftcard__learn">
        Learned from
        {draft.learned_from.map((s) => (
          <Link key={s.id} className="tagchip" to={`/library/prompts/${s.id}`}>
            {s.title}
          </Link>
        ))}
        <span className="muted">Their constraints were carried into the draft.</span>
      </p>
      <div className="draftcard__acts">
        <button type="button" className="btn btn--inline" onClick={() => open({ kind: 'prompt', draft })}>
          <Plus size={16} strokeWidth={2.4} /> Save and contribute
        </button>
        <button
          type="button"
          className="btn-outline"
          onClick={() => void navigator.clipboard?.writeText(draft.body).then(() => setCopied(true)).catch(() => undefined)}
        >
          <Copy size={15} strokeWidth={2.2} /> {copied ? 'Copied' : 'Copy'}
        </button>
        <button type="button" className="btn-outline" onClick={onAnother} disabled={busy}>
          {busy ? <Loader2 className="spin" size={15} aria-hidden="true" /> : <RotateCcw size={15} strokeWidth={2.2} />} Try another
          version
        </button>
      </div>
      <p className="answer__foot">
        <ShieldCheck size={14} strokeWidth={2.2} aria-hidden="true" /> A contributed prompt goes to the Data Privacy Office
        before anyone else can run it.
      </p>
    </section>
  )
}

/** recommend(user, task), laid open: the two contexts, and how the graph ran. */
function WhyThis({ user, task, plan }: { user: UserContext; task: TaskContext; plan: Plan }) {
  const t = plan.timings_ms
  const serial = plan.selected_pillars.map((p) => t[`pillar ${p}`] ?? 0).reduce((a, b) => a + b, 0)
  const parallel = t['pillars (parallel)'] ?? 0
  return (
    <details className="why">
      <summary>
        <Info size={14} strokeWidth={2.2} aria-hidden="true" /> How this was chosen
      </summary>
      <div className="why__grid">
        <section>
          <h4 className="why__title">You</h4>
          <dl className="why__list">
            <dt>Role</dt>
            <dd>
              {user.persona_label} <span className="why__note">({user.persona_rule})</span>
            </dd>
            <dt>Function</dt>
            <dd>{user.function || 'Not in your directory profile'}</dd>
            <dt>Interests</dt>
            <dd>{user.role_interests.join(', ') || 'None set for this role'}</dd>
            <dt>Maturity</dt>
            <dd>
              {MATURITY_LABEL[user.maturity]} <span className="why__note">{user.maturity_basis}</span>
            </dd>
            <dt>Access</dt>
            <dd>{user.entitlements.join(', ') || 'No groups'}</dd>
          </dl>
        </section>
        <section>
          <h4 className="why__title">This request</h4>
          <dl className="why__list">
            <dt>{task.intents.length > 1 ? 'Intents' : 'Intent'}</dt>
            <dd>
              {task.intents.map((i) => INTENT_LABEL[i]).join(', then ')}
              {task.intent_cue ? <span className="why__note"> (you said &ldquo;{task.intent_cue}&rdquo;)</span> : null}
            </dd>
            <dt>Activity</dt>
            <dd>
              {task.activity ? task.activity.title : 'Not one of your mapped jobs'}
              {task.carried_over && <span className="why__note"> (carried over from this conversation)</span>}
            </dd>
            <dt>Objective</dt>
            <dd>{task.objective || 'Not stated'}</dd>
            <dt>Subject</dt>
            <dd>
              {task.subject ? (
                <>
                  {task.subject.name}{' '}
                  <span className="why__note">
                    ({task.subject_carried_over ? 'carried over from this conversation; ' : ''}this conversation only, not
                    saved to your profile)
                  </span>
                </>
              ) : (
                'None named'
              )}
            </dd>
            <dt>Needs</dt>
            <dd>{task.needs.join(', ') || 'Not mapped'}</dd>
            <dt>Sensitivity</dt>
            <dd>
              {SENSITIVITY_LABEL[task.sensitivity]} <span className="why__note">{task.sensitivity_reason}</span>
            </dd>
            {task.ordering && (
              <>
                <dt>Order</dt>
                <dd>{task.ordering}</dd>
              </>
            )}
          </dl>
        </section>
        <section className="why__flow">
          <h4 className="why__title">How the hub worked</h4>
          <ol className="why__steps">
            <li>
              <b>Conversation</b>
              <span>
                {plan.opening ? (
                  <>
                    Set aside <q>{plan.opening}</q>; the rest went on as a task.
                  </>
                ) : (
                  'A task, so it went through the full flow.'
                )}
              </span>
            </li>
            <li>
              <b>Security, data and policy</b>
              <span>
                Classified {SENSITIVITY_LABEL[task.sensitivity].toLowerCase()}. {MODEL_ACCESS[plan.model_access]} Searches and
                usage logs saw: <q>{plan.sanitized_query}</q>
              </span>
            </li>
            <li>
              <b>Understand</b>
              <span>
                {plan.plan_source === 'claude' ? `Planned by ${plan.model}.` : 'Planned by rules, no model call.'}{' '}
                {plan.plan_reason}
              </span>
            </li>
            <li>
              <b>Policy on the plan</b>
              <ul>
                {plan.governance.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </li>
            <li>
              <b>Pillars, in parallel</b>
              {plan.subqueries.length ? (
                <ul>
                  {plan.subqueries.map((s) => (
                    <li key={s.pillar}>
                      {PILLAR_LABEL[s.pillar]}: <q>{s.query}</q>
                      {s.reformulated && <span className="why__note"> (rewritten for this pillar)</span>}
                      <span className="why__note"> · {t[`pillar ${s.pillar}`] ?? 0} ms</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span>None asked.</span>
              )}
            </li>
            <li>
              <b>Reply</b>
              <span>
                {plan.reply_source === 'claude' ? `Written by ${plan.model}.` : 'Written from the catalogue.'}{' '}
                {plan.reply_reason}
              </span>
            </li>
            <li>
              <b>Time</b>
              <span>
                {duration(t.total ?? 0)} in all
                {t.understand >= 1000 || t.synthesize >= 1000
                  ? `, of which the model took ${duration((t.understand ?? 0) + (t.synthesize ?? 0))}`
                  : ', with no model call'}
                .
                {parallel + 5 < serial
                  ? ` The pillars ran side by side: ${duration(parallel)}, against ${duration(serial)} one after another.`
                  : plan.subqueries.length > 0 && ` The pillars took ${duration(parallel)}.`}
              </span>
            </li>
          </ol>
        </section>
      </div>
    </details>
  )
}

/** The answer while it streams in: understood, planned, each pillar as it lands, the reply as it is written. */
const AGENT_NAME: Record<PillarName, string> = {
  prompts: 'Prompts & Skills agent',
  marketplace: 'Discover agent',
  learning: 'Learning agent',
  community: 'Community search',
}

/** The agentic flow as it runs: the request read, each agent searching and judging, the answer written. */
function LiveSteps({ live, waiting }: { live: Live; waiting: PillarName[] }) {
  const read = live.plannedBy !== null && live.task !== null
  const steps: { id: string; label: string; done: boolean }[] = [
    {
      id: 'read',
      label: !read
        ? 'Reading your request'
        : live.plannedBy === 'claude'
          ? 'Claude read your request and chose where to look'
          : 'Read your request',
      done: read,
    },
    ...live.pillars.map((p) => {
      const g = live.groups.find((x) => x.pillar === p)
      return {
        id: p,
        label: g
          ? `${AGENT_NAME[p]} found ${g.hits.length}${g.reranked ? ', judged by Claude' : ''}`
          : `${AGENT_NAME[p]} is searching`,
        done: !!g,
      }
    }),
  ]
  if (read && waiting.length === 0) steps.push({ id: 'write', label: 'Writing the answer', done: live.replyDone })
  return (
    <ol className="livesteps" aria-label="Progress">
      {steps.map((s) => (
        <li key={s.id} className={s.done ? 'livesteps__done' : 'livesteps__now'}>
          {s.done ? (
            <Check size={14} strokeWidth={2.6} aria-hidden="true" />
          ) : (
            <Loader2 className="spin" size={14} aria-hidden="true" />
          )}
          {s.label}
        </li>
      ))}
    </ol>
  )
}

function LiveAnswer({ live }: { live: Live }) {
  const { task } = live
  const waiting = live.pillars.filter((p) => !live.groups.some((g) => g.pillar === p))
  // In the plan's order once there is a plan; in arrival order before it.
  const order = live.pillars.length ? live.pillars : live.groups.map((g) => g.pillar)
  const found = order.flatMap((p) => live.groups.filter((g) => g.pillar === p && g.hits.length))
  return (
    <div className="answer" aria-busy="true">
      {live.intents.length === 0 ? (
        // A conversational reply streams straight in, with nothing to understand first.
        !live.reply && (
          <p className="answer__loading">
            <Loader2 className="spin" size={16} aria-hidden="true" /> Understanding your request
          </p>
        )
      ) : (
        <p className="answer__meta">
          {live.intents.map((i) => (
            <span key={i} className="intent">
              {INTENT_LABEL[i]}
            </span>
          ))}
          {task?.activity && <>for {task.activity.title}</>}
        </p>
      )}
      {task && <ContextChips task={task} />}

      {live.intents.length > 0 && <LiveSteps live={live} waiting={waiting} />}

      {live.reply && <p className={`answer__reply${live.replyDone ? '' : ' caret'}`}>{live.reply}</p>}

      {live.recommended.length > 0 && (
        <Group
          icon={Layers}
          title={task?.activity ? `For ${task.activity.title.toLowerCase()}` : 'For this job'}
          count={live.recommended.length}
        >
          <AssetList variant="cards" assets={live.recommended.slice(0, RECOMMENDED)} journeyId={task?.activity?.id ?? ''} />
        </Group>
      )}
      {found.map((g) => (
        <PillarGroupView key={g.pillar} group={g} />
      ))}
    </div>
  )
}

/** What the hub can do, each with a request to try. */
function Capabilities({ caps, onAsk }: { caps: AskResponse['capabilities']; onAsk: (q: string) => void }) {
  return (
    <ul className="caps" aria-label="What the AI Hub can do">
      {caps.map((c) => (
        <li key={c.intent} className="cap">
          <span className="intent">{c.label}</span>
          <p className="cap__what">{c.what}</p>
          <button type="button" className="suggest suggest--chip" onClick={() => onAsk(c.example)}>
            {c.example}
          </button>
        </li>
      ))}
    </ul>
  )
}

/** Small talk and help, answered by the conversation gate: no search, no model. */
function DirectAnswer({ ask, latest, onAsk }: { ask: AskResponse; latest: boolean; onAsk: (q: string) => void }) {
  return (
    <div className="answer">
      <p className="answer__reply">{ask.reply}</p>
      {ask.capabilities.length > 0 && <Capabilities caps={ask.capabilities} onAsk={onAsk} />}
      {latest && ask.follow_ups.length > 0 && (
        <div className="followups" role="group" aria-label="Try asking">
          {ask.follow_ups.map((f) => (
            <button key={f.query} type="button" className="suggest suggest--chip" onClick={() => onAsk(f.query)}>
              {f.label}
            </button>
          ))}
        </div>
      )}
      <p className="answer__foot">
        <Info size={14} strokeWidth={2.2} aria-hidden="true" /> Answered directly in {duration(ask.took_ms)}: no search
        ran{ask.reply_source === 'claude' ? '.' : ' and no model was called.'}
      </p>
    </div>
  )
}

/**
 * One reply in the home conversation. The job's own toolkit when the request
 * is one of the person's jobs; then what each pillar found; a prompt written
 * for them when they asked for one. Nothing is shown that the catalogue does
 * not hold.
 */
export function AssistantAnswer({
  turn,
  latest,
  onAsk,
  onRated,
}: {
  turn: Turn
  latest: boolean
  onAsk: (q: string) => void
  onRated: (id: number, helpful: boolean) => void
}) {
  const { pillars } = useHub()
  // A draft they asked for after the answer arrived; the answer's own otherwise.
  const [ownDraft, setOwnDraft] = useState<Draft | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [draftError, setDraftError] = useState('')

  if (turn.status === 'loading')
    return turn.live ? (
      <LiveAnswer live={turn.live} />
    ) : (
      <p className="answer__loading">
        <Loader2 className="spin" size={16} aria-hidden="true" /> Looking across the hub
      </p>
    )
  if (turn.status === 'error' || !turn.ask)
    return (
      <div className="answer__error" role="alert">
        <p>{turn.error ?? 'The hub could not answer just now.'}</p>
        <button type="button" className="suggest suggest--chip" onClick={() => onAsk(turn.q)}>
          Try again
        </button>
      </div>
    )

  const a = turn.ask
  if (a.kind !== 'task' || !a.task || !a.plan) return <DirectAnswer ask={a} latest={latest} onAsk={onAsk} />
  const task = a.task
  const plan = a.plan
  const turnId = a.turn_id
  const draft = ownDraft ?? a.draft
  const activity = task.activity
  const groups: PillarGroup[] = a.pillars.filter((g) => g.hits.length)
  const listed = new Set(groups.flatMap((g) => g.hits.map((h) => h.href)))
  // Pages only from the pillars the plan asked: a request for an agent is not
  // answered with Community's pages too.
  const asked = pillars.filter((p) => (plan.selected_pillars as string[]).includes(p.id))
  // A follow-up's pages are matched with the topic it was read with, as its searches were.
  const matched = plan.follows_on ? `${turn.q} ${plan.follows_on}` : turn.q
  const pages = activity ? [] : matchSections(asked, matched, SHOWN).filter((h) => !listed.has(h.section.href))
  const nothing = !activity && !groups.length && !pages.length
  // Nothing matched a request that named no task: the hub says what it can do instead.
  const offerCapabilities = a.capabilities.length > 0
  const canDraft =
    !draft && !offerCapabilities && task.sensitivity !== 'confidential' && (nothing || task.intents.includes('contribute'))

  const recordOpen = (ref: string) => {
    if (turnId) void openedFromTurn(turnId, ref).catch(() => undefined)
  }
  const opened = (hit: PillarHit) => {
    recordOpen(hit.ref)
    track('hub', 'click', { subject_id: hit.ref, subject_type: hit.kind, meta: { intent: task.intent } })
  }

  async function makeDraft(goal: string, variant: boolean) {
    setDrafting(true)
    setDraftError('')
    try {
      setOwnDraft(await draftPrompt(goal, variant))
    } catch (e) {
      setDraftError(e instanceof Error ? e.message : 'The draft could not be written. Try again.')
    } finally {
      setDrafting(false)
    }
  }

  function rate(helpful: boolean) {
    onRated(turn.id, helpful)
    if (turnId) void rateTurn(turnId, helpful).catch(() => undefined)
  }

  return (
    <div className="answer">
      <p className="answer__meta">
        {task.intents.map((i) => (
          <span key={i} className="intent">
            {INTENT_LABEL[i]}
          </span>
        ))}
        {activity && (
          <>
            for <Link to={`/journeys/${activity.id}`}>{activity.title}</Link>
          </>
        )}
        {task.intent_cue && <span className="answer__cue">because you said &ldquo;{task.intent_cue}&rdquo;</span>}
      </p>

      <ContextChips task={task} followsOn={plan.follows_on} />

      <p className="answer__reply">{a.reply}</p>

      {offerCapabilities && <Capabilities caps={a.capabilities} onAsk={onAsk} />}

      {activity && a.recommended.length > 0 && (
        <Group
          icon={Layers}
          title={`For ${activity.title.toLowerCase()}`}
          count={a.recommended.length}
          link={{ to: `/journeys/${activity.id}?intent=${task.intent}`, label: 'Open the journey' }}
        >
          <AssetList variant="cards" assets={a.recommended.slice(0, RECOMMENDED)} journeyId={activity.id} onOpen={recordOpen} />
        </Group>
      )}

      {groups.map((g) => (
        <PillarGroupView key={g.pillar} group={g} onOpen={opened} />
      ))}

      {pages.length > 0 && (
        <Group icon={Layers} title="Across the hub" count={pages.length}>
          <ul className="airows">
            {pages.map(({ pillar, section }) => (
              <HitRow
                key={section.href}
                hit={{ ref: `page:${section.href}`, kind: 'page', title: section.title, summary: '', href: section.href, why: '', meta: pillar.short_title }}
                onOpen={() => track('hub', 'click', { subject_id: section.href, subject_type: 'page' })}
              />
            ))}
          </ul>
        </Group>
      )}

      {draft ? (
        <DraftCard draft={draft} busy={drafting} onAnother={() => void makeDraft(draft.goal, !draft.variant)} />
      ) : (
        canDraft && (
          <div className="authoroffer">
            <PenLine size={18} strokeWidth={2.2} aria-hidden="true" />
            <div>
              <b>Want one written for you?</b>
              <span className="muted">I can draft a prompt for this from the validated ones on your desk.</span>
            </div>
            <button type="button" className="btn btn--inline" disabled={drafting} onClick={() => void makeDraft(task.loggable_query, false)}>
              {drafting ? <Loader2 className="spin" size={15} aria-hidden="true" /> : <PenLine size={15} strokeWidth={2.2} />} Draft a
              prompt
            </button>
          </div>
        )
      )}
      {draftError && (
        <p className="state state--error" role="alert">
          {draftError}
        </p>
      )}

      {nothing && !draft && !offerCapabilities && (
        <p className="answer__empty">
          Or ask for it through <Link to="/intake/new">AI Requests</Link>, so the team can see the need.
        </p>
      )}

      {latest && a.follow_ups.length > 0 && (
        <div className="followups" role="group" aria-label="Suggested follow-ups">
          {a.follow_ups.map((f) => (
            <button key={f.query} type="button" className="suggest suggest--chip" onClick={() => onAsk(f.query)}>
              {f.label}
            </button>
          ))}
        </div>
      )}

      <div className="answer__rate" role="group" aria-label="Was this answer helpful?">
        {turn.helpful === undefined ? (
          <>
            <span>Was this helpful?</span>
            <button type="button" className="ratebtn" onClick={() => rate(true)}>
              <ThumbsUp size={14} strokeWidth={2.2} aria-hidden="true" /> Yes
            </button>
            <button type="button" className="ratebtn" onClick={() => rate(false)}>
              <ThumbsDown size={14} strokeWidth={2.2} aria-hidden="true" /> No
            </button>
          </>
        ) : (
          <span className="muted">Thanks. Recorded against this answer, without your question.</span>
        )}
      </div>

      <WhyThis user={a.user} task={task} plan={plan} />

      {!nothing && (
        <p className="answer__foot">
          <ShieldCheck size={14} strokeWidth={2.2} aria-hidden="true" /> Everything here comes from the hub&rsquo;s
          catalogue. Anything its owner has not confirmed says so.
        </p>
      )}
    </div>
  )
}
