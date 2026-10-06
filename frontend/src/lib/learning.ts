import { getJson, postJson } from './api'
export type ItemType = 'video' | 'course' | 'confluence' | 'guide' | 'documentation' | 'quick-reference' | 'best-practice'
export type LearningStatus = 'not_started' | 'in_progress' | 'completed'

export interface LearningPath {
  id: string
  title: string
  blurb: string
  steps: string[]
  owner: string
  completed_steps: number
  total_steps: number
  next_item_id: string | null
}

export interface Item {
  id: string
  title: string
  type: ItemType
  description: string
  topics: string[]
  capabilities: string[]
  personas: string[]
  required_for: string[]
  path: string
  level: string
  duration_seconds: number
  tags: string[]
  related_agents: string[]
  url: string
  youtube_id: string
  poster_url: string
  source: string
  /** Catalogue courses: the provider's own id, who teaches it, its lessons and outcomes. */
  provider_ref?: string
  instructor?: string
  lessons?: { title: string; minutes: number; kind: 'Video' | 'Lecture' | 'Chapter' }[]
  outcomes?: string[]
  /** False when MUFG holds no licence for it yet. */
  licensed?: boolean
  body: string
  source_kind: 'sample' | 'enterprise'
  owner: string
  prerequisites: string[]
  recommendation_reason: string
  blocked_by: string[]
  prerequisite_unavailable: boolean
  sequence: number | null
  status: LearningStatus
  progress: number
  required: boolean
  rating_count: number
  /** null until the item clears the minimum rating count; an average of one vote is noise. */
  rating_average: number | null
  /** Shrunk toward the catalogue mean. Not displayed; this is what a future ranker would sort on. */
  rating_weighted: number | null
  my_rating: number | null
  /** Where Start opens: Pluralsight (single sign-on, or a search until connected) or the Microsoft Learn page. */
  launch_url?: string
  /** True when the content reads inside the hub (Microsoft Learn). */
  read_in_hub?: boolean
  /** True when the provider's own API supplied the details just now. */
  live?: boolean
}

export const PROVIDERS = ['Pluralsight', 'Microsoft Learn'] as const
export type Provider = (typeof PROVIDERS)[number]

export interface LearnLink {
  title: string
  url: string
}

/** A Microsoft Learn module, path or unit, read through Microsoft's Learn MCP server. */
export interface LearnPage {
  url: string
  title: string
  kind: string
  count: string
  level: string
  minutes: number | null
  summary: string
  objectives: string[]
  prerequisites: string
  units: LearnLink[]
  markdown: string
}

/** A result from a provider's own library, beyond the hub's catalogue. */
export interface ProviderResult {
  title: string
  /** A Microsoft Learn page (reads in the hub), or where the course opens on Pluralsight. */
  url: string
  excerpt: string
  level: string
  duration_seconds: number
  read_in_hub: boolean
}

export interface ProviderResults {
  provider: Provider
  /** live: searched just now. sample: not connected, catalogue only. blocked: the provider refused. */
  state: 'live' | 'sample' | 'blocked'
  note: string
  results: ProviderResult[]
}

export const fetchLearnPage = (url: string, signal?: AbortSignal) =>
  getJson<LearnPage>(`/api/learning/microsoft-learn/page?url=${encodeURIComponent(url)}`, signal)

/** The Learning search beyond the catalogue: Pluralsight and Microsoft Learn, together. */
export const searchProviders = (q: string, signal?: AbortSignal) =>
  getJson<ProviderResults[]>(`/api/learning/providers/search?q=${encodeURIComponent(q)}`, signal)

/** The hub's reader for a Microsoft Learn page. */
export function readerHref(url: string, itemId?: string) {
  return `/learning/read?url=${encodeURIComponent(url)}${itemId ? `&item=${encodeURIComponent(itemId)}` : ''}`
}

export interface ItemDetail extends Item {
  path_title: string
  related_items: Item[]
  related_agent_names: Record<string, string>
}

export interface Section {
  id: string
  title: string
  subtitle: string
  items: Item[]
}

export interface LearningHome {
  persona: string
  persona_label: string
  paths: LearningPath[]
  role_paths: LearningPath[]
  sections: Section[]
  item_count: number
}

export interface TopicCoverage {
  topic: string
  completed: number
  total: number
}

export interface MyLearning {
  persona: string
  persona_label: string
  completed: number
  in_progress: number
  not_started: number
  required_total: number
  required_completed: number
  items: Item[]
  coverage: TopicCoverage[]
  proficiency_note: string
}

export const fetchLearningHome = (persona: string, signal?: AbortSignal) =>
  getJson<LearningHome>(`/api/learning${persona ? `?persona=${encodeURIComponent(persona)}` : ''}`, signal)

export const fetchItems = (params: Record<string, string>, signal?: AbortSignal) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
  return getJson<Item[]>(`/api/learning/items${qs ? `?${qs}` : ''}`, signal)
}

export const fetchItem = (id: string, signal?: AbortSignal) => getJson<ItemDetail>(`/api/learning/items/${encodeURIComponent(id)}`, signal)

export const fetchMyLearning = (signal?: AbortSignal) => getJson<MyLearning>('/api/learning/my-learning', signal)

/** Learning owns this capability; the marketplace agent page only consumes it. */
export const fetchAgentLearning = (agentId: string, persona: string, signal?: AbortSignal) =>
  getJson<Item[]>(
    `/api/learning/for-agent/${encodeURIComponent(agentId)}${persona ? `?persona=${encodeURIComponent(persona)}` : ''}`,
    signal,
  )

/** Learning state, owned by the Learning pillar. Separate from hub footprints. */
export async function recordProgress(item_id: string, status: LearningStatus, progress?: number) {
  return postJson<Item>('/api/learning/progress', { item_id, status, progress })
}

/** Rate an item you have opened. Pass null to withdraw your rating. */
export async function rateItem(item_id: string, stars: number | null) {
  return postJson<Item>('/api/learning/ratings', { item_id, stars })
}

/** Deep link to an item, remembering where the user came from so Back works. */
export function itemHref(itemId: string, fromAgentId?: string) {
  return `/learning/items/${encodeURIComponent(itemId)}${fromAgentId ? `?from=${encodeURIComponent(fromAgentId)}` : ''}`
}

export const TYPE_LABEL: Record<ItemType, string> = {
  video: 'Video',
  course: 'Course',
  confluence: 'Confluence',
  guide: 'Guide',
  documentation: 'Documentation',
  'quick-reference': 'Quick reference',
  'best-practice': 'Best practice',
}

/** A real picture for an item: its own poster, or YouTube's for the video it plays. Empty when it has neither. */
export function thumbnail(item: Pick<Item, 'poster_url' | 'youtube_id'>): string {
  if (item.poster_url) return item.poster_url
  return item.youtube_id ? `https://i.ytimg.com/vi/${encodeURIComponent(item.youtube_id)}/hqdefault.jpg` : ''
}

/** A provider's badge or logo (an SVG), shown at its own size rather than filling the cover like a photo. */
export function isBadge(url: string): boolean {
  return /\.svg(\?|$)/i.test(url)
}

export function duration(seconds: number): string {
  if (!seconds) return ''
  const m = Math.round(seconds / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}
