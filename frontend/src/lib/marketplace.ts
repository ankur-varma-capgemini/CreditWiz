import { getJson, postJson } from './api'
export type AgentStatus = 'production' | 'pilot' | 'beta' | 'in_development' | 'deprecated'
export type AccessType = 'open' | 'request' | 'restricted'

/** A link to one of the agent's documents where it lives. Blank values have not been confirmed. */
export interface AgentDocument {
  /** A document type from the knowledge sources: brd, asd, hld, lld. */
  type: string
  /** The system it lives in; blank until confirmed. */
  system: string
  url: string
  /** What this document covers, in the owning team's words; blank uses the document type's description. */
  description: string
}

export interface Agent {
  source_kind: 'sample' | 'enterprise'
  id: string
  name: string
  tagline: string
  version: string
  description: string
  problem_solved: string
  business_domains: string[]
  use_cases: string[]
  capabilities: string[]
  services: string[]
  example_tasks: string[]
  personas: string[]
  category: string
  owner: { team: string; name: string; email: string }
  status: AgentStatus
  platform: string
  tools_services: string[]
  models: string[]
  architecture_pattern: string
  access: { type: AccessType; how: string; launch_url: string; request_url: string }
  documentation_url: string
  architecture_url: string
  /** Its documents by type, linked where they live. Nexus keeps no copies. */
  documents: AgentDocument[]
  tags: string[]
  featured: boolean
  popularity: number
  created_at: string
  updated_at: string
}

export interface Persona {
  id: string
  label: string
  description: string
  interests: { domains: string[]; capabilities: string[]; tags: string[] }
}

export interface Carousel {
  id: string
  title: string
  subtitle: string
  agents: Agent[]
}

export interface MarketplaceHome {
  persona: string
  personas: Persona[]
  domains: string[]
  carousels: Carousel[]
  agent_count: number
  example_queries: string[]
}

export interface SearchIntent {
  summary: string
  concepts: string[]
  domains: string[]
  capabilities: string[]
  keywords: string[]
}

export interface AgentMatch {
  agent: Agent
  score: number
  why: string
  reasons: string[]
  /** Share of the understood request this agent covers, 0-100; null when nothing was extracted. */
  coverage: number | null
}

export interface SearchResponse {
  query: string
  intent: SearchIntent
  engine: 'claude' | 'fusion'
  results: AgentMatch[]
  no_match: boolean
  next_steps: { label: string; href: string }[]
}

// Footprints and feedback live in the shared hub layer: see lib/context.ts

export function fetchMarketplaceHome(persona: string, signal?: AbortSignal, domain = '') {
  const qs = '?' + new URLSearchParams({ ...(persona ? { persona } : {}), ...(domain && domain !== 'all' ? { domain } : {}) }).toString()
  return getJson<MarketplaceHome>(`/api/marketplace/home${qs}`, signal)
}

export function fetchAgents(params: Record<string, string>, signal?: AbortSignal) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
  return getJson<Agent[]>(`/api/marketplace/agents${qs ? `?${qs}` : ''}`, signal)
}

export function fetchAgent(id: string, signal?: AbortSignal) {
  return getJson<Agent>(`/api/marketplace/agents/${encodeURIComponent(id)}`, signal)
}

export function fetchRelated(id: string, signal?: AbortSignal) {
  return getJson<Agent[]>(`/api/marketplace/agents/${encodeURIComponent(id)}/related`, signal)
}

export function searchAgents(query: string, persona: string, domain: string, signal?: AbortSignal) {
  return postJson<SearchResponse>('/api/marketplace/search', { query, persona: persona || null, domain: domain || null, limit: 6 }, signal)
}

export const STATUS_LABEL: Record<AgentStatus, string> = {
  production: 'Production',
  pilot: 'Pilot',
  beta: 'Beta',
  in_development: 'In development',
  deprecated: 'Deprecated',
}

export const ACCESS_LABEL: Record<AccessType, string> = {
  open: 'Open to all employees',
  request: 'Request access',
  restricted: 'Restricted',
}
