import { getJson } from './api'

export type SystemKind = 'wiki' | 'document_site' | 'work_tracking' | 'service_management' | 'document_store'

/** Where content lives. Blank owner and location have not been confirmed by the owning team. */
export interface SourceSystem {
  id: string
  name: string
  kind: SystemKind
  /** What it would feed in Nexus: a proposal, not an agreed integration. */
  feeds: string
  owner: string
  location: string
  connection: 'not_connected' | 'connected'
}

/** What the content is. Blank values have not been confirmed by the team. */
export interface DocumentType {
  id: string
  abbreviation: string
  name: string
  about: string
  feeds: string
  lives_in: string[]
  owner: string
}

export interface LinkGroup {
  id: string
  name: string
  systems: string[]
}

export interface KnowledgeSources {
  systems: SourceSystem[]
  document_types: DocumentType[]
  link_groups: LinkGroup[]
}

export const SYSTEM_KIND_LABEL: Record<SystemKind, string> = {
  wiki: 'Wiki',
  document_site: 'Document site',
  work_tracking: 'Work tracking',
  service_management: 'Service management',
  document_store: 'Document store',
}

export const fetchKnowledgeSources = (signal?: AbortSignal) =>
  getJson<KnowledgeSources>('/api/knowledge/sources', signal)
