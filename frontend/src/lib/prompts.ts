import { getJson, postJson, requestJson } from './api'

export type Risk = 'Low' | 'Medium' | 'High'
/** Where a prompt was made, relative to the viewer. */
export type Relation = 'team' | 'dept' | 'other'
export type Sort = 'relevance' | 'used' | 'rated' | 'new' | 'saved'

export interface DeskRef {
  id: string
  label: string
}

export interface Person {
  name: string
  initials: string
  team: string
}

export interface PromptCard {
  id: string
  desk: DeskRef
  category: string
  title: string
  description: string
  tags: string[]
  relation: Relation
  uses: number
  rating: number
  ratings: number
  hours_saved: number
  risk: Risk
  validated: boolean
  contributor: Person
  updated: string
  saved: boolean
  source_kind: 'sample' | 'enterprise'
}

export interface LibraryPage {
  /** The viewer's desk; null when their job title is on no desk. */
  desk: DeskRef | null
  showing: string
  desks: DeskRef[]
  categories: string[]
  total: number
  prompts: PromptCard[]
}

export interface PromptInput {
  label: string
  type: string
  note: string
  required: boolean
}

export interface Review {
  name: string
  initials: string
  team: string
  stars: number
  when: string
  comment: string
}

export interface PromptDetail extends PromptCard {
  views: number
  repetition: string
  narrative: string
  created: string
  risk_note: string
  tutorial: { title: string; duration: string; views: string } | null
  inputs: PromptInput[]
  guidelines: string[]
  body: string
  sample_output: string
  reviews: Review[]
  collaborators: { name: string; initials: string; role: string }[]
  related: PromptCard[]
}

export interface Template {
  id: string
  name: string
  use: string
  when: string
  body: string
}

export interface PromptRef {
  id: string
  title: string
}

/** A prompt written from validated ones. Nothing is saved until it is contributed. */
export interface Draft {
  goal: string
  title: string
  description: string
  category: string
  tags: string[]
  body: string
  learned_from: PromptRef[]
  variant: boolean
}

export interface Safety {
  client_data: boolean
  mnpi: boolean
  feeds_control: boolean
}

export type Submission =
  | {
      kind: 'prompt'
      title: string
      description: string
      category: string
      tags: string[]
      scope: Relation
      body: string
      inputs: string[]
      hours_saved: number | null
      safety: Safety
      guidelines: string[]
      tested: true
      learned_from: string[]
    }
  | { kind: 'video'; title: string; description: string; recording: string }
  | { kind: 'agent'; title: string; description: string; chain: string[] }

export type ContributionKind = Submission['kind']

export interface Contribution {
  id: string
  kind: ContributionKind
  title: string
  description: string
  status: 'in_review' | 'live' | 'returned'
  review: string
  risk: Risk | null
  /** Who may find it once approved. Its author can from the moment it is submitted. */
  audience: Audience
  created_at: string
}

export type Audience = 'team' | 'department' | 'everyone'

export const AUDIENCE_LABEL: Record<Audience, string> = {
  team: 'your desk',
  department: 'your department',
  everyone: 'everyone on Nexus',
}

export const RELATION_LABEL: Record<Relation, string> = {
  team: 'Your team',
  dept: 'Your department',
  other: 'Another desk',
}

export const SORTS: [Sort, string][] = [
  ['relevance', 'All'],
  ['used', 'Most used'],
  ['rated', 'Top rated'],
  ['new', 'New'],
  ['saved', 'Saved'],
]

export const KIND_NAME: Record<ContributionKind, string> = {
  prompt: 'Prompt',
  video: 'Skill video',
  agent: 'AI agent proposal',
}

/**
 * The library for one desk, or all of them. Search runs in the browser over
 * what this returns, so what someone types into the library search, which can
 * name a client, never travels in a URL.
 */
export const fetchLibrary = (desk: string, signal?: AbortSignal) =>
  getJson<LibraryPage>(`/api/prompts?desk=${encodeURIComponent(desk)}`, signal)

export const fetchMyDeskLibrary = (signal?: AbortSignal) => getJson<LibraryPage>('/api/prompts', signal)

export const fetchPrompt = (id: string, signal?: AbortSignal) =>
  getJson<PromptDetail>(`/api/prompts/${encodeURIComponent(id)}`, signal)

export const fetchTemplates = (signal?: AbortSignal) => getJson<Template[]>('/api/prompts/templates', signal)

export const setSaved = (id: string, saved: boolean) =>
  requestJson<{ saved: boolean }>(`/api/prompts/${encodeURIComponent(id)}/saved`, { method: saved ? 'PUT' : 'DELETE' })

export const draftPrompt = (goal: string, variant: boolean) => postJson<Draft>('/api/prompts/draft', { goal, variant })

export const submitContribution = (s: Submission) => postJson<Contribution>('/api/contributions', s)

export const fetchMyContributions = (signal?: AbortSignal) =>
  getJson<Contribution[]>('/api/contributions/mine', signal)
