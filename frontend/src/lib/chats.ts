import { useSyncExternalStore } from 'react'
import type { Turn } from '../components/home/AssistantAnswer'
import type { AskResponse } from './journeys'

/**
 * Home's conversations, to come back to as in Claude or ChatGPT.
 *
 * Kept in this browser, per account, and never sent to the hub to keep: a
 * question can name a client, and the hub's servers hold ids only (see
 * hub/telemetry.py). A question still being answered lives in memory, so an
 * answer keeps arriving in its own conversation while another one is open.
 */
export interface Chat {
  id: string
  /** The person's own name for it; null until they rename it. */
  title: string | null
  created_at: string
  updated_at: string
  /** The hub's id for the conversation, which ties its turns together in telemetry. */
  session_id: string
  turns: Turn[]
}

const PREFIX = 'mufg.chats.'
const MAX_CHATS = 50
const MAX_TURNS = 30
const TITLE = 60
const NONE: Chat[] = []

const cache = new Map<string, Chat[]>()
const listeners = new Set<() => void>()

function now() {
  return new Date().toISOString()
}

function read(user: string): Chat[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(PREFIX + user) ?? '[]')
    return Array.isArray(raw)
      ? (raw as Chat[]).filter((c) => c && typeof c.id === 'string' && Array.isArray(c.turns) && c.turns.length > 0)
      : []
  } catch {
    return []
  }
}

function chatsOf(user: string): Chat[] {
  if (!user) return NONE
  let chats = cache.get(user)
  if (!chats) {
    chats = read(user)
    cache.set(user, chats)
  }
  return chats
}

/** Answered turns only. When the browser runs out of room, the oldest conversations go first. */
function persist(user: string) {
  const kept = chatsOf(user)
    .map((c) => ({ ...c, turns: c.turns.filter((t) => t.status === 'done').slice(-MAX_TURNS) }))
    .filter((c) => c.turns.length > 0)
    .slice(0, MAX_CHATS)
  for (let n = kept.length; n > 0; n--) {
    try {
      localStorage.setItem(PREFIX + user, JSON.stringify(kept.slice(0, n)))
      return
    } catch {
      /* full: try again without the oldest */
    }
  }
  try {
    localStorage.removeItem(PREFIX + user)
  } catch {
    /* storage may be unavailable */
  }
}

function change(user: string, fn: (chats: Chat[]) => Chat[], save: boolean) {
  const next = fn(chatsOf(user)).sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  cache.set(user, next)
  if (save) persist(user)
  listeners.forEach((listener) => listener())
}

function onTurn(user: string, chatId: string, turnId: number, fn: (turn: Turn) => Turn, save: boolean) {
  change(
    user,
    (chats) => chats.map((c) => (c.id === chatId ? { ...c, turns: c.turns.map((t) => (t.id === turnId ? fn(t) : t)) } : c)),
    save,
  )
}

// Another tab saved: take its copy, keeping any answer this tab is still waiting for.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (!event.key?.startsWith(PREFIX)) return
    const user = event.key.slice(PREFIX.length)
    const before = cache.get(user)
    if (!before) return
    const waiting = before.filter((c) => c.turns.some((t) => t.status !== 'done'))
    cache.set(user, read(user))
    change(
      user,
      (stored) => [
        ...stored.map((c) => {
          const own = waiting.find((w) => w.id === c.id)
          return own ? { ...c, turns: [...c.turns, ...own.turns.filter((t) => t.status !== 'done')] } : c
        }),
        ...waiting.filter((w) => !stored.some((c) => c.id === w.id)),
      ],
      false,
    )
  })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** This person's conversations, most recently active first. */
export function useChats(user: string): Chat[] {
  return useSyncExternalStore(subscribe, () => chatsOf(user))
}

/** What a conversation is called: its own name, else its first request. */
export function chatTitle(chat: Chat): string {
  if (chat.title) return chat.title
  // Small talk ("hi") makes a poor title; the first real request names it.
  const first = chat.turns.find((t) => t.ask?.kind === 'task') ?? chat.turns[0]
  if (!first) return 'New conversation'
  const q = first.q.replace(/\s+/g, ' ').trim()
  return q.length > TITLE ? `${q.slice(0, TITLE - 1).trimEnd()}…` : q
}

/** Enough to recognise a conversation without opening it. */
export interface ChatPreview {
  title: string
  /** The latest answer, flattened to one line; blank while the first one arrives. */
  last: string
  /** What the latest answered request found, by place: Learning 1, Discover 2. */
  found: { label: string; count: number }[]
  questions: number
  answering: boolean
}

export function chatPreview(chat: Chat): ChatPreview {
  const latest = (pick: (t: Turn) => boolean) => [...chat.turns].reverse().find(pick)
  const answered = latest((t) => t.status === 'done' && !!t.ask)
  const task = latest((t) => t.status === 'done' && t.ask?.kind === 'task')
  return {
    title: chatTitle(chat),
    last: (answered?.ask?.reply ?? '').replace(/\s+/g, ' ').trim(),
    found: (task?.ask?.pillars ?? []).filter((g) => g.hits.length > 0).map((g) => ({ label: g.label, count: g.hits.length })),
    questions: chat.turns.length,
    answering: chat.turns.some((t) => t.status === 'loading'),
  }
}

/** Its name or anything asked in it. */
export function chatMatches(chat: Chat, words: string): boolean {
  const needle = words.trim().toLowerCase()
  return !needle || [chatTitle(chat), ...chat.turns.map((t) => t.q)].some((text) => text.toLowerCase().includes(needle))
}

const DAY = 86_400_000

/** Today, Yesterday, Previous 7 days, Older: by when each was last used, newest first. */
export function byDay(chats: Chat[], at = new Date()): { label: string; chats: Chat[] }[] {
  const today = new Date(at.getFullYear(), at.getMonth(), at.getDate()).getTime()
  const label = (iso: string) => {
    const t = new Date(iso).getTime()
    if (t >= today) return 'Today'
    if (t >= today - DAY) return 'Yesterday'
    if (t >= today - 7 * DAY) return 'Previous 7 days'
    return 'Older'
  }
  const out: { label: string; chats: Chat[] }[] = []
  for (const chat of chats) {
    const name = label(chat.updated_at)
    const group = out.find((g) => g.label === name)
    if (group) group.chats.push(chat)
    else out.push({ label: name, chats: [chat] })
  }
  return out
}

export function startChat(user: string): Chat {
  const at = now()
  const chat: Chat = { id: crypto.randomUUID(), title: null, created_at: at, updated_at: at, session_id: '', turns: [] }
  change(user, (chats) => [chat, ...chats].slice(0, MAX_CHATS), false)
  return chat
}

/** A question, as it is asked. Kept in memory until it is answered. */
export function addTurn(user: string, chatId: string, turn: Turn) {
  change(user, (chats) => chats.map((c) => (c.id === chatId ? { ...c, updated_at: now(), turns: [...c.turns, turn] } : c)), false)
}

/** The answer as it streams in: memory only. */
export function updateTurn(user: string, chatId: string, turnId: number, fn: (turn: Turn) => Turn) {
  onTurn(user, chatId, turnId, fn, false)
}

/** The whole answer: saved, with the hub's id for the conversation. */
export function finishTurn(user: string, chatId: string, turnId: number, ask: AskResponse) {
  const done = (t: Turn): Turn => ({ ...t, status: 'done', ask, live: undefined })
  change(
    user,
    (chats) =>
      chats.map((c) =>
        c.id === chatId
          ? { ...c, session_id: ask.session_id, updated_at: now(), turns: c.turns.map((t) => (t.id === turnId ? done(t) : t)) }
          : c,
      ),
    true,
  )
}

export function rateTurn(user: string, chatId: string, turnId: number, helpful: boolean) {
  onTurn(user, chatId, turnId, (t) => ({ ...t, helpful }), true)
}

export function renameChat(user: string, chatId: string, title: string) {
  change(user, (chats) => chats.map((c) => (c.id === chatId ? { ...c, title: title.trim().slice(0, 120) || null } : c)), true)
}

export function deleteChat(user: string, chatId: string) {
  change(user, (chats) => chats.filter((c) => c.id !== chatId), true)
}
