import * as Popover from '@radix-ui/react-popover'
import {
  Bot,
  ChevronDown,
  Clock,
  GraduationCap,
  Layers,
  MessageSquare,
  MessagesSquare,
  Pencil,
  Search,
  Sparkles,
  SquarePen,
  Trash2,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { byDay, chatMatches, chatPreview, deleteChat, renameChat, useChats, type Chat } from '../../lib/chats'
import { timeAgo } from '../../lib/community'
import '../../conversations.css'

const RECENT = 3

const hrefOf = (chat: Chat) => `/super-agent?chat=${encodeURIComponent(chat.id)}`

function questions(n: number) {
  return `${n} ${n === 1 ? 'question' : 'questions'}`
}

// Each place the hub searches, as the answers name it.
const PLACE_ICON: Record<string, LucideIcon> = {
  Prompts: Sparkles,
  Agents: Bot,
  Learning: GraduationCap,
  Community: Users,
}

/**
 * Every conversation, searchable, newest first: open one, rename it or delete
 * it without leaving the page. Opened from a conversation's title and from
 * "All conversations" on home.
 */
function ConversationList({ userId, current, onDone }: { userId: string; current?: string; onDone: () => void }) {
  const chats = useChats(userId)
  const navigate = useNavigate()
  const [words, setWords] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  // Escape leaves a rename without saving, even if leaving the field blurs it.
  const cancelled = useRef(false)
  const shown = chats.filter((c) => chatMatches(c, words))

  function rename(chat: Chat, value: string) {
    setRenaming(null)
    if (cancelled.current) return
    if (value.trim() && value.trim() !== chatPreview(chat).title) renameChat(userId, chat.id, value)
  }

  function remove(chat: Chat) {
    setDeleting(null)
    deleteChat(userId, chat.id)
    if (chat.id === current) {
      onDone()
      navigate('/super-agent', { replace: true })
    }
  }

  return (
    <div className="convos">
      <label className="convos__search">
        <Search size={15} strokeWidth={2.2} aria-hidden="true" />
        <input value={words} onChange={(e) => setWords(e.target.value)} placeholder="Search conversations" aria-label="Search conversations" />
      </label>
      <Link to="/super-agent" className="convos__new" onClick={onDone}>
        <span className="convos__new-icon">
          <SquarePen size={14} strokeWidth={2.2} aria-hidden="true" />
        </span>
        New conversation
      </Link>
      <div className="convos__scroll">
        {shown.length === 0 ? (
          <p className="convos__empty">{words.trim() ? `No conversations match “${words.trim()}”.` : 'No conversations yet.'}</p>
        ) : (
          byDay(shown).map((group) => (
            <div key={group.label}>
              <h3 className="convos__when">{group.label}</h3>
              <ul className="convos__list">
                {group.chats.map((chat) => {
                  const p = chatPreview(chat)
                  if (deleting === chat.id) {
                    return (
                      <li key={chat.id} className="convos__confirm">
                        <span>Delete “{p.title}”?</span>
                        <span className="convos__actions">
                          <button type="button" className="convos__btn convos__btn--danger" onClick={() => remove(chat)}>
                            Delete
                          </button>
                          <button type="button" className="convos__btn" onClick={() => setDeleting(null)}>
                            Cancel
                          </button>
                        </span>
                      </li>
                    )
                  }
                  return (
                    <li key={chat.id} className={`convos__row${chat.id === current ? ' is-current' : ''}`}>
                      {renaming === chat.id ? (
                        <input
                          className="convos__rename"
                          defaultValue={p.title}
                          aria-label="Conversation name"
                          maxLength={120}
                          autoFocus
                          onFocus={(e) => e.currentTarget.select()}
                          onBlur={(e) => rename(chat, e.currentTarget.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') e.currentTarget.blur()
                            if (e.key === 'Escape') {
                              cancelled.current = true
                              setRenaming(null)
                            }
                          }}
                        />
                      ) : (
                        <>
                          <Link
                            to={hrefOf(chat)}
                            className="convos__open"
                            aria-current={chat.id === current ? 'page' : undefined}
                            onClick={onDone}
                          >
                            <span className="convos__title">{p.title}</span>
                            <span className="convos__meta">
                              {p.answering ? (
                                <span className="convos__live">Answering…</span>
                              ) : (
                                timeAgo(chat.updated_at)
                              )}
                              <span aria-hidden="true">·</span>
                              {questions(p.questions)}
                              {p.found.length > 0 && (
                                <>
                                  <span aria-hidden="true">·</span>
                                  {p.found.map((f) => `${f.label} ${f.count}`).join(', ')}
                                </>
                              )}
                            </span>
                          </Link>
                          <span className="convos__tools">
                            <button
                              type="button"
                              className="convos__tool"
                              aria-label={`Rename “${p.title}”`}
                              title="Rename"
                              onClick={() => {
                                cancelled.current = false
                                setDeleting(null)
                                setRenaming(chat.id)
                              }}
                            >
                              <Pencil size={14} strokeWidth={2.2} />
                            </button>
                            <button
                              type="button"
                              className="convos__tool convos__tool--danger"
                              aria-label={`Delete “${p.title}”`}
                              title="Delete"
                              onClick={() => setDeleting(chat.id)}
                            >
                              <Trash2 size={14} strokeWidth={2.2} />
                            </button>
                          </span>
                        </>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/**
 * The list in a popover (Radix): kept on screen near an edge, focus moved in
 * and given back, closed by a pick, a click outside or Escape. Escape while
 * renaming ends the rename only.
 */
function ConversationsPopover({
  userId,
  current,
  align,
  trigger,
}: {
  userId: string
  current?: string
  align: 'start' | 'end'
  /** The button that opens it; Radix gives it aria-expanded and data-state. */
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="switcher__panel"
          side="bottom"
          align={align}
          sideOffset={8}
          collisionPadding={16}
          aria-label="Your conversations"
          onEscapeKeyDown={(e) => {
            if ((document.activeElement as HTMLElement | null)?.classList.contains('convos__rename')) e.preventDefault()
          }}
        >
          <ConversationList userId={userId} current={current} onDone={() => setOpen(false)} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

/**
 * A conversation's title, which opens every conversation: switching is two
 * clicks from anywhere in a conversation, since its header stays in view.
 */
export function ConversationSwitcher({ userId, chat }: { userId: string; chat: Chat }) {
  return (
    <div className="switcher">
      <h1 className="switcher__heading">
        <ConversationsPopover
          userId={userId}
          current={chat.id}
          align="start"
          trigger={
            <button type="button" className="switcher__button" title="Your conversations">
              <span className="switcher__title">{chatPreview(chat).title}</span>
              <ChevronDown size={16} strokeWidth={2.2} aria-hidden="true" />
            </button>
          }
        />
      </h1>
    </div>
  )
}

/**
 * Home's latest conversations, under the composer: each says what it was
 * about, how it ended and what was found, so carrying on is one click.
 */
export function RecentConversations({ userId }: { userId: string }) {
  const chats = useChats(userId)
  if (chats.length === 0) return null
  return (
    <section className="recent" aria-labelledby="recent-title">
      <div className="recent__head">
        <h2 className="recent__title" id="recent-title">
          <MessagesSquare size={16} strokeWidth={2.2} aria-hidden="true" /> Recent conversations
        </h2>
        <ConversationsPopover
          userId={userId}
          align="end"
          trigger={
            <button type="button" className="recent__all-button">
              All conversations <span className="recent__count">{chats.length}</span>
              <ChevronDown size={14} strokeWidth={2.4} aria-hidden="true" />
            </button>
          }
        />
      </div>
      <div className="recent__grid">
        {chats.slice(0, RECENT).map((chat) => {
          const p = chatPreview(chat)
          return (
            <Link key={chat.id} to={hrefOf(chat)} className="recent__card">
              <span className="recent__name">{p.title}</span>
              <span className="recent__last">{p.answering ? 'Answering…' : p.last || 'No answer yet.'}</span>
              {p.found.length > 0 && (
                <span className="recent__found">
                  {p.found.map((f) => {
                    const Icon = PLACE_ICON[f.label] ?? Layers
                    return (
                      <span key={f.label} className="found">
                        <Icon size={12} strokeWidth={2.2} aria-hidden="true" /> {f.label} <b>{f.count}</b>
                      </span>
                    )
                  })}
                </span>
              )}
              <span className="recent__foot">
                <span>
                  <Clock size={12} strokeWidth={2.2} aria-hidden="true" /> {timeAgo(chat.updated_at)}
                </span>
                <span>
                  <MessageSquare size={12} strokeWidth={2.2} aria-hidden="true" /> {questions(p.questions)}
                </span>
              </span>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
