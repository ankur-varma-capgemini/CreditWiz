import { getJson, postJson, requestJson } from './api'

/** Community as the hub shows it. Viva Engage when connected; the hub's sample content until then. */
export type PostKind = 'discussion' | 'question' | 'announcement' | 'praise'

export interface Person {
  id: string
  name: string
  title: string
}

export interface Community {
  id: string
  name: string
  description: string
  privacy: 'public' | 'private'
  member_count: number | null
  topics: string[]
  personas: string[]
  web_url: string
}

export interface Post {
  id: string
  thread_id: string
  community_id: string
  author: Person
  created_at: string
  kind: PostKind
  title: string
  body: string
  topics: string[]
  like_count: number
  liked_by_me: boolean
  reply_count: number
  web_url: string
}

export interface Reply {
  id: string
  thread_id: string
  author: Person
  created_at: string
  body: string
  like_count: number
  /** Written in this hub while Viva Engage is not connected: saved here and posted nowhere else. */
  local: boolean
}

export interface Thread {
  post: Post
  replies: Reply[]
}

export interface Expert {
  person: Person
  topics: string[]
  community_ids: string[]
}

export interface Connection {
  source: 'viva_engage' | 'sample'
  connected: boolean
  notice: string
}

export interface CommunityHome {
  connection: Connection
  communities: Community[]
  mine: string[]
  suggested: Community[]
  experts: Expert[]
}

export interface Feed {
  connection: Connection
  community: Community | null
  posts: Post[]
}

const qs = (params: Record<string, string | undefined>) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString()
  return s ? `?${s}` : ''
}

export const fetchCommunityHome = (persona: string, signal?: AbortSignal) =>
  getJson<CommunityHome>(`/api/community${qs({ persona })}`, signal)

export const fetchFeed = (params: { community?: string; kind?: PostKind | ''; q?: string; persona: string }, signal?: AbortSignal) =>
  getJson<Feed>(`/api/community/feed${qs({ ...params, kind: params.kind || undefined })}`, signal)

export const fetchThread = (id: string, persona: string, signal?: AbortSignal) =>
  getJson<Thread>(`/api/community/threads/${encodeURIComponent(id)}${qs({ persona })}`, signal)

export const postReply = (id: string, body: string, persona: string) =>
  postJson<Reply>(`/api/community/threads/${encodeURIComponent(id)}/replies${qs({ persona })}`, { body })

/** Like a post, or take the like back. Live, it reaches Viva Engage as the signed-in person. */
export const setLike = (id: string, liked: boolean, persona: string) =>
  requestJson<Post>(`/api/community/posts/${encodeURIComponent(id)}/like${qs({ persona })}`, { method: liked ? 'POST' : 'DELETE' })

/** "3h ago", "yesterday", "4d ago", then the date. */
export function timeAgo(iso: string, now = Date.now()): string {
  const minutes = Math.floor((now - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

/** One of six muted avatar tones, stable per person. */
export function tone(id: string): number {
  let h = 0
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return h % 6
}
