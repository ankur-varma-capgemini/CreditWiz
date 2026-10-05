import { Bell, LogOut, Menu, Plus, Search, Settings, User } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchNotifications, isAbort, searchHub, postJson, announceSessionChange } from '../lib/api'
import { useCreate } from '../lib/create'
import type { CurrentUser, Notification, SearchResult } from '../lib/types'
import { useClickOutside } from '../lib/useClickOutside'

interface Props {
  user: CurrentUser
  /** Opens the navigation drawer. Only rendered below the desktop breakpoint. */
  onMenu?: () => void
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  if (h < 1) return 'just now'
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return d === 1 ? 'yesterday' : `${d}d ago`
}

export function TopBar({ user, onMenu }: Props) {
  const navigate = useNavigate()
  const create = useCreate()

  // ---- search
  const [query, setQuery] = useState('')
  const [searchError, setSearchError] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const searchRef = useRef<HTMLDivElement>(null)
  useClickOutside(
    searchRef,
    useCallback(() => setSearchOpen(false), []),
  )

  useEffect(() => {
    const q = query.trim()
    if (!q) return
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      searchHub(q, ctrl.signal)
        .then((r) => {
          setResults(r)
          setHighlight(0)
        })
        .catch((err: unknown) => {
          if (!isAbort(err)) {
            setResults([])
            setSearchError('Search could not load. Try again.')
          }
        })
    }, 160)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [query])

  function go(href: string) {
    setSearchOpen(false)
    setQuery('')
    navigate(href)
  }

  // The suggestions come from the hub's own catalogs, as fast as typing. The
  // last row searches everywhere: Pluralsight, Microsoft Learn and Community
  // too, which are too slow, and too rate-limited, to ask on every keystroke.
  function searchEverywhere() {
    const q = query.trim()
    setSearchOpen(false)
    setQuery('')
    navigate(`/search?q=${encodeURIComponent(q)}`)
  }

  function onSearchKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!results || results.length === 0) {
      // Enter is the reflex after typing a question; honour it rather than
      // leaving the person staring at an empty menu.
      if (e.key === 'Enter' && query.trim() && !searchError) {
        e.preventDefault()
        searchEverywhere()
      }
      return
    }
    // The suggestions, then the "search everywhere" row.
    const rows = results.length + 1
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => (h + 1) % rows)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => (h - 1 + rows) % rows)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlight < results.length) go(results[highlight].href)
      else searchEverywhere()
    }
  }

  // ---- notifications
  const [actionError, setActionError] = useState('')
  const [notes, setNotes] = useState<Notification[] | null>(null)
  const [notesOpen, setNotesOpen] = useState(false)
  const notesRef = useRef<HTMLDivElement>(null)
  useClickOutside(
    notesRef,
    useCallback(() => setNotesOpen(false), []),
  )

  useEffect(() => {
    if (!notesOpen || notes !== null) return
    const ctrl = new AbortController()
    fetchNotifications(ctrl.signal)
      .then(setNotes)
      .catch((err: unknown) => {
        if (!isAbort(err)) setActionError('Notifications could not load. Reopen this menu to retry.')
      })
    return () => ctrl.abort()
  }, [notesOpen, notes])

  const unread = notes ? notes.filter((n) => !n.read).length : user.unread_notifications

  async function markAllRead() {
    try {
      await postJson('/api/notifications/read', {})
      setNotes((prev) => prev?.map((n) => ({ ...n, read: true })) ?? prev)
      setActionError('')
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not save notifications')
    }
  }
  async function signOut() {
    try {
      await postJson('/api/auth/logout', {})
      announceSessionChange()
      window.dispatchEvent(new Event('creditwiz:signed-out'))
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not sign out')
    }
  }

  // ---- account
  const [acctOpen, setAcctOpen] = useState(false)
  const acctRef = useRef<HTMLDivElement>(null)
  useClickOutside(
    acctRef,
    useCallback(() => setAcctOpen(false), []),
  )

  const showResults = searchOpen && !!query.trim() && results !== null

  return (
    <header className="topbar">
      <button type="button" className="topbar__menu" onClick={onMenu} aria-label="Open navigation">
        <Menu size={20} strokeWidth={2.2} />
      </button>
      <div className="search" ref={searchRef}>
        <Search className="search__icon" strokeWidth={2.2} />
        <input
          className="search__input"
          type="search"
          placeholder="Search across AI Hub"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setResults(null)
            setSearchError('')
            setSearchOpen(true)
          }}
          onFocus={() => setSearchOpen(true)}
          onKeyDown={onSearchKey}
          aria-label="Search the AI Hub"
          aria-expanded={showResults}
          aria-controls="hub-search-results"
          autoComplete="off"
        />
        {showResults && (
          <div className="menu search__results" id="hub-search-results" role="listbox">
            {results.length === 0 ? (
              searchError ? (
                <div className="menu__empty">{searchError}</div>
              ) : (
                <button
                  type="button"
                  className="search__result search__result--fallback is-highlight"
                  role="option"
                  aria-selected="true"
                  onClick={searchEverywhere}
                >
                  <span className="search__kind search__kind--action">search</span>
                  <span>Search everywhere for “{query.trim()}”</span>
                </button>
              )
            ) : (
              <>
                {results.map((r, i) => (
                  <button
                    key={r.href}
                    type="button"
                    className={`search__result${i === highlight ? ' is-highlight' : ''}`}
                    role="option"
                    aria-selected={i === highlight}
                    onMouseEnter={() => setHighlight(i)}
                    onClick={() => go(r.href)}
                  >
                    <span className={`search__kind search__kind--${r.kind}`}>{r.kind}</span>
                    <span>{r.title}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className={`search__result search__result--fallback${highlight === results.length ? ' is-highlight' : ''}`}
                  role="option"
                  aria-selected={highlight === results.length}
                  onMouseEnter={() => setHighlight(results.length)}
                  onClick={searchEverywhere}
                >
                  <span className="search__kind search__kind--action">search</span>
                  <span>Search everywhere for “{query.trim()}”</span>
                </button>
              </>
            )}
          </div>
        )}
      </div>

      <div className="topbar__actions">
        {actionError && (
          <span role="alert" className="state--error">
            {actionError}
          </span>
        )}
        <button type="button" className="btn btn--inline btn--create" onClick={() => create.open({ kind: 'choose' })}>
          <Plus size={18} strokeWidth={2.4} aria-hidden="true" />
          <span>Create new</span>
        </button>
        <div className="menu-anchor" ref={notesRef}>
          <button
            type="button"
            className={`iconbtn${notesOpen ? ' is-open' : ''}`}
            aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
            aria-haspopup="menu"
            aria-expanded={notesOpen}
            onClick={() => setNotesOpen((o) => !o)}
          >
            <Bell strokeWidth={2} size={26} />
            {unread > 0 && <span className="iconbtn__badge">{unread}</span>}
          </button>
          {notesOpen && (
            <div className="menu menu--notes" role="menu">
              <div className="menu__head">
                <span>Notifications</span>
                {unread > 0 && (
                  <button type="button" className="menu__action" onClick={markAllRead}>
                    Mark all read
                  </button>
                )}
              </div>
              {notes === null && <div className="menu__empty">Loading…</div>}
              {notes && notes.length === 0 && <div className="menu__empty">You're all caught up.</div>}
              {notes?.map((n) => (
                <Link
                  key={n.id}
                  to={n.href}
                  className={`note${n.read ? '' : ' is-unread'}`}
                  role="menuitem"
                  onClick={() => setNotesOpen(false)}
                >
                  <span className="note__dot" aria-hidden="true" />
                  <span className="note__body">
                    <span className="note__title">{n.title}</span>
                    <span className="note__text">{n.body}</span>
                    <span className="note__time">{timeAgo(n.created_at)}</span>
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="menu-anchor" ref={acctRef}>
          <button
            type="button"
            className="avatar"
            aria-label={`Account: ${user.display_name}`}
            aria-haspopup="menu"
            aria-expanded={acctOpen}
            onClick={() => setAcctOpen((o) => !o)}
          >
            {user.initials}
          </button>
          {acctOpen && (
            <div className="menu menu--account" role="menu">
              <div className="account">
                <span className="avatar avatar--sm" aria-hidden="true">
                  {user.initials}
                </span>
                <span>
                  <span className="account__name">{user.display_name}</span>
                  <span className="account__role">
                    {user.job_title}
                    {user.department ? ` · ${user.department}` : ''}
                  </span>
                  <span className="account__role">
                    Persona: {user.persona.label}
                    {user.is_admin ? ' · Hub admin' : ''}
                  </span>
                </span>
              </div>
              <Link to="/settings" className="menu__item" role="menuitem" onClick={() => setAcctOpen(false)}>
                <User size={18} strokeWidth={2} /> View profile
              </Link>
              <Link to="/settings" className="menu__item" role="menuitem" onClick={() => setAcctOpen(false)}>
                <Settings size={18} strokeWidth={2} /> Settings
              </Link>
              <button type="button" className="menu__item" role="menuitem" onClick={() => void signOut()}>
                <LogOut size={18} strokeWidth={2} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
