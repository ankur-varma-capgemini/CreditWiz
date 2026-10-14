import { getJson, postJson } from './api'
/**
 * Shared Nexus user-context client.
 *
 *   ALL PILLARS -> track()/sendFeedback() -> /api/context/*  -> shared footprint store
 *
 * No pillar owns this. Marketplace, Learning and every future pillar call the
 * same functions so one user context is assembled across Nexus.
 */

export type Pillar =
  'marketplace' | 'prompts' | 'learning' | 'intake' | 'governance' | 'knowledge' | 'community' | 'insights' | 'platform' | 'hub'

export type EventType =
  | 'search'
  | 'view'
  | 'click'
  | 'launch'
  | 'request_access'
  | 'documentation_click'
  | 'architecture_click'
  | 'collaborate'
  | 'learning_view'
  | 'learning_complete'
  | 'feedback_positive'
  | 'feedback_negative'

export interface InterestSignal {
  topic: string
  weight: number
  events: number
  pillars: string[]
}

export type Maturity = 'beginner' | 'developing' | 'experienced'

/** Who the person is, as Nexus understands them. A profile, not a memory. */
export interface UserContext {
  user_id: string
  display_name: string
  job_title: string
  department: string
  business_unit: string
  persona: string
  persona_label: string
  persona_rule: string
  function: string
  role_interests: string[]
  /** Observed from footprints; not used for ranking. */
  interests: InterestSignal[]
  /** Inferred; `maturity_basis` says from what. */
  maturity: Maturity
  maturity_basis: string
  entitlements: string[]
  event_count: number
  pillars_seen: string[]
}

interface TrackPayload {
  subject_id?: string
  subject_type?: string
  query?: string
  persona?: string
  topics?: string[]
  meta?: Record<string, unknown>
}

const JSON_HEADERS = { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CreditWiz-Request': '1' }

/** Fire-and-forget footprint. Never throws, never blocks the UI. */
export function track(pillar: Pillar, type: EventType, data: TrackPayload = {}) {
  try {
    const body = JSON.stringify({ pillar, type, ...data })
    void fetch('/api/context/events', { method: 'POST', headers: JSON_HEADERS, body, keepalive: true }).catch(() => {})
  } catch {
    /* footprints are best-effort */
  }
}

export async function sendFeedback(body: {
  pillar: Pillar
  context: string
  helpful: boolean
  subject_id?: string
  query?: string
  persona?: string
  missing?: string
}) {
  return postJson<{ ok: boolean; id: string }>('/api/context/feedback', body)
}

export async function fetchUserContext(signal?: AbortSignal) {
  return getJson<UserContext>('/api/context/me', signal)
}
