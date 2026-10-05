import { ApiError, getJson, postJson } from './api'
import type { UserContext } from './context'
import type { Draft } from './prompts'

/** Why someone came to the hub. Decided by the backend from what they typed. */
export type Intent = 'find' | 'learn' | 'improve' | 'ask' | 'contribute'

export const INTENTS: Intent[] = ['find', 'learn', 'improve', 'ask', 'contribute']

export const INTENT_LABEL: Record<Intent, string> = {
  find: 'Find',
  learn: 'Learn',
  improve: 'Improve',
  ask: 'Ask',
  contribute: 'Contribute',
}

export const INTENT_HINT: Record<Intent, string> = {
  find: 'The systems and data you work from.',
  learn: 'Get better at the job.',
  improve: 'Do it faster, with AI.',
  ask: 'People and answers.',
  contribute: 'Share what works.',
}

export const KIND_LABEL: Record<string, string> = {
  agent: 'Agent',
  learning: 'Learning',
  system: 'System of record',
  data_product: 'Data product',
  prompt: 'Prompt',
  expert: 'Expert',
  community: 'Community',
  use_case: 'Use case',
}

/** Blank fields have not been confirmed by the owning team. */
export interface Trust {
  owner_team: string
  owner_name: string
  purpose: string
  approved_by: string
  approved_on: string
  who_can_use: string
  how_to_access: string
  guardrails: string[]
  feedback: string
}

export interface AssetCard {
  ref: string
  kind: string
  title: string
  summary: string
  intent: Intent
  why: string
  status: string
  provided_by: string
  action_label: string
  action_url: string
  trust: Trust
  source_kind: 'sample' | 'enterprise'
}

export interface JourneySummary {
  id: string
  title: string
  summary: string
  systems: string[]
  asset_count: number
}

export interface JourneysHome {
  persona: string
  persona_label: string
  examples: string[]
  journeys: JourneySummary[]
}

export interface JourneyStep {
  title: string
  detail: string
}

export interface SystemRole {
  system: string
  does: string
}

export interface JourneyPage {
  id: string
  persona: string
  persona_label: string
  title: string
  summary: string
  steps: JourneyStep[]
  systems: SystemRole[]
  assets: AssetCard[]
}

export interface FollowUp {
  label: string
  query: string
}

export type Sensitivity = 'public' | 'internal' | 'confidential' | 'client_confidential'

export const SENSITIVITY_LABEL: Record<Sensitivity, string> = {
  public: 'Public',
  internal: 'Internal',
  confidential: 'Confidential',
  client_confidential: 'Client confidential',
}

/** A client or deal the request names. Lives for the conversation only. */
export interface Subject {
  name: string
  kind: 'client' | 'deal'
}

/** What the person is doing right now, built per request on the server. */
export interface TaskContext {
  /** The primary intent; `intents` holds every one the request carries, primary first. */
  intent: Intent
  intents: Intent[]
  intent_cue: string
  objective: string
  activity: JourneySummary | null
  carried_over: boolean
  subject: Subject | null
  subject_carried_over: boolean
  needs: string[]
  sensitivity: Sensitivity
  sensitivity_reason: string
  /** The only form of the request that may go to usage logs. */
  loggable_query: string
  ordering: string
}

export type PillarName = 'prompts' | 'marketplace' | 'learning' | 'community'

export interface SubQuery {
  pillar: PillarName
  query: string
  /** True when the planner rewrote the request for this pillar. */
  reformulated: boolean
}

export interface PillarHit {
  ref: string
  kind: string
  title: string
  summary: string
  /** Blank when the owning team has not confirmed where it lives. */
  href: string
  why: string
  meta: string
  /** How the agent judged it against the request; absent when the model was not asked. */
  fit?: 'strong' | 'partial' | null
}

export interface PillarGroup {
  pillar: PillarName
  label: string
  href: string
  query: string
  hits: PillarHit[]
  ms: number
  /** How the pillar's agent found them: meaning and exact words fused, exact words alone, or word matching. */
  retrieval: 'hybrid' | 'keyword' | 'words'
  /** True when the model read the shortlist against the request and ordered it. */
  reranked: boolean
}

/** How the answer was put together: the graph's own account of itself. */
export interface Plan {
  /** A greeting or thanks the conversation gate set aside before routing. */
  opening: string
  /** What every search and the usage log saw: names, accounts and emails masked. */
  sanitized_query: string
  /** What the data policy let the model receive for this request. */
  model_access: 'as_typed' | 'masked' | 'none'
  subqueries: SubQuery[]
  selected_pillars: PillarName[]
  plan_source: 'claude' | 'rules'
  plan_reason: string
  reply_source: 'claude' | 'rules'
  reply_reason: string
  governance: string[]
  timings_ms: Record<string, number>
  model: string
  /** The earlier topic a follow-up was read with ("IFRS 9"); blank when it stood alone. */
  follows_on: string
}

/** What the conversation gate made of a request. Only a task is planned and searched. */
export type ConversationKind = 'greeting' | 'small_talk' | 'thanks' | 'goodbye' | 'help' | 'task'

/** One of the hub's five capabilities, with a request to try. */
export interface Capability {
  intent: Intent
  label: string
  what: string
  example: string
}

export interface AskResponse {
  kind: ConversationKind
  /** Null for small talk, which is answered directly and not recorded. */
  turn_id: string | null
  session_id: string
  query: string
  user: UserContext
  /** A task's context and plan; null for small talk. */
  task: TaskContext | null
  plan: Plan | null
  /** The job's own toolkit, when the request is one of the person's jobs. */
  recommended: AssetCard[]
  pillars: PillarGroup[]
  draft: Draft | null
  /** For help, and for a request nothing in the hub matched. */
  capabilities: Capability[]
  reply: string
  /** Who wrote the reply: the model, or a fixed line from the catalogue or the conversation gate. */
  reply_source: 'claude' | 'rules'
  follow_ups: FollowUp[]
  took_ms: number
}

export const PILLAR_LABEL: Record<PillarName, string> = {
  prompts: 'Prompt library',
  marketplace: 'Discover',
  learning: 'Learning',
  community: 'Community',
}

const withPersona = (persona: string) => (persona ? `?persona=${encodeURIComponent(persona)}` : '')

export const fetchJourneys = (persona: string, signal?: AbortSignal) =>
  getJson<JourneysHome>(`/api/journeys${withPersona(persona)}`, signal)

export const fetchJourney = (id: string, persona: string, signal?: AbortSignal) =>
  getJson<JourneyPage>(`/api/journeys/${encodeURIComponent(id)}${withPersona(persona)}`, signal)

/** What the conversation was on, for follow-ups that name neither, and which conversation it is. */
export interface AskContext {
  journey?: string
  subject?: string
  session?: string
  /** The conversation's earlier requests, oldest first, for a follow-up ("is there one for it?") to be read with. */
  history?: string[]
}

/** What the hub sends while it answers, in the order it happens. */
export type HubEvent =
  | { type: 'accepted'; session_id: string }
  /** `provisional`: the rules' first reading, sent while the model plans. */
  | { type: 'task_understood'; intents: Intent[]; planned_by: 'claude' | 'rules'; reason: string; provisional?: boolean }
  | {
      type: 'plan_ready'
      task: TaskContext
      pillars: PillarName[]
      subqueries: { pillar: PillarName; query: string }[]
      governance: string[]
    }
  | { type: 'toolkit'; recommended: AssetCard[]; provisional?: boolean }
  | { type: 'pillar_result'; group: PillarGroup; provisional?: boolean }
  | { type: 'response_delta'; delta: string }
  | { type: 'response'; reply: string; reply_source: 'claude' | 'rules'; draft: Draft | null; follow_ups: FollowUp[] }
  | { type: 'complete'; response: AskResponse }
  | { type: 'error'; message: string }

/** An answer as it arrives, before the whole of it has. */
export interface Live {
  intents: Intent[]
  /** True while what is shown is the first reading and the model is still planning. */
  refining: boolean
  /** Who planned it, once the plan is made. */
  plannedBy: 'claude' | 'rules' | null
  task: TaskContext | null
  pillars: PillarName[]
  groups: PillarGroup[]
  recommended: AssetCard[]
  reply: string
  /** True once the final reply has replaced whatever streamed. */
  replyDone: boolean
}

export const startLive = (): Live => ({
  intents: [],
  refining: false,
  plannedBy: null,
  task: null,
  pillars: [],
  groups: [],
  recommended: [],
  reply: '',
  replyDone: false,
})

/** Folds one event into what the page shows while the answer streams in. */
export function reduceLive(live: Live, e: HubEvent): Live {
  switch (e.type) {
    case 'task_understood':
      return { ...live, intents: e.intents, refining: !!e.provisional, plannedBy: e.provisional ? null : e.planned_by }
    case 'plan_ready':
      // The plan replaces the first reading: pillars it did not keep go now,
      // the rest are replaced as their results arrive.
      return {
        ...live,
        task: e.task,
        intents: e.task.intents,
        pillars: e.pillars,
        refining: false,
        groups: live.groups.filter((g) => e.pillars.includes(g.pillar)),
      }
    // Only what the model's plan asked for is shown: nothing unvetted.
    case 'toolkit':
      return e.provisional ? live : { ...live, recommended: e.recommended }
    case 'pillar_result':
      return e.provisional ? live : { ...live, groups: [...live.groups.filter((g) => g.pillar !== e.group.pillar), e.group] }
    case 'response_delta':
      return live.replyDone ? live : { ...live, reply: live.reply + e.delta }
    case 'response':
      // The final reply wins over what streamed: a streamed model reply that
      // did not stick to what was found is replaced by the catalogue's.
      return { ...live, reply: e.reply, replyDone: true }
    default:
      return live
  }
}

/**
 * Event-driven progressive response: each event is handed to `onEvent` as it
 * arrives, and the whole answer is returned at the end. Posted, not an
 * EventSource GET, so the question never travels in a URL.
 */
export async function askHubStream(
  q: string,
  persona: string,
  context: AskContext,
  onEvent: (e: HubEvent) => void,
  signal?: AbortSignal,
): Promise<AskResponse> {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-CreditWiz-Request': '1' },
    body: JSON.stringify({
      q,
      persona: persona || null,
      journey: context.journey || null,
      subject: context.subject || null,
      session: context.session || null,
      history: context.history ?? [],
    }),
    signal,
  })
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null)
    if (res.status === 401) window.dispatchEvent(new Event('creditwiz:signed-out'))
    throw new ApiError(res.status, typeof body?.detail === 'string' ? body.detail : `Request failed (${res.status}). Please try again.`)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffered = ''
  let answer: AskResponse | null = null
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffered += value
    let end: number
    while ((end = buffered.indexOf('\n\n')) >= 0) {
      const block = buffered.slice(0, end)
      buffered = buffered.slice(end + 2)
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (!data) continue
      const event = JSON.parse(data) as HubEvent
      if (event.type === 'error') throw new Error(event.message)
      if (event.type === 'complete') answer = event.response
      onEvent(event)
    }
  }
  if (!answer) throw new Error('The hub stopped before it finished answering. Try again.')
  return answer
}

export const rateTurn = (turnId: string, helpful: boolean) =>
  postJson<{ ok: boolean }>(`/api/ask/turns/${encodeURIComponent(turnId)}/feedback`, { helpful })

/** Which recommendation they opened. Ids only; the server keeps refs the answer showed. */
export const openedFromTurn = (turnId: string, ref: string) =>
  postJson<{ ok: boolean }>(`/api/ask/turns/${encodeURIComponent(turnId)}/selected`, { ref })
