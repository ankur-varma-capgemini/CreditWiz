import {
  Award,
  ChevronRight,
  Compass,
  ExternalLink,
  HelpCircle,
  Home,
  Lock,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  Search,
  ShieldCheck,
  Star,
  ThumbsUp,
  UserCheck,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import {
  fetchCommunityHome,
  fetchFeed,
  fetchThread,
  initials,
  postReply,
  setLike,
  timeAgo,
  tone,
  type Community,
  type CommunityHome,
  type Feed,
  type Post,
  type PostKind,
  type Thread,
} from '../../lib/community'
import { fetchItems, type Item } from '../../lib/learning'
import { usePersona } from '../../lib/personaContext'
import { subjectIcon, toneFor } from '../../lib/visuals'
import { Cover } from '../Cover'
import { CourseDrawer } from '../learning/CourseDrawer'
import { CourseCard } from '../learning/ProviderShelves'
import '../../community.css'

/** The Community pillar's own sections, as views of one feed. */
const VIEWS: Record<string, { title: string; kind?: PostKind; icon: typeof Home }> = {
  '': { title: 'Home', icon: Home },
  forums: { title: 'Discussions', kind: 'discussion', icon: MessagesSquare },
  faqs: { title: 'Questions', kind: 'question', icon: HelpCircle },
  announcements: { title: 'Announcements', kind: 'announcement', icon: Megaphone },
  stories: { title: 'Success stories', kind: 'praise', icon: Award },
  experts: { title: 'SME directory', icon: UserCheck },
}
const KIND_LABEL: Record<PostKind, string> = { discussion: '', question: 'Question', announcement: 'Announcement', praise: 'Success story' }
const FAVOURITES = 'mufg.community.favourites'

function readFavourites(): string[] {
  try {
    return JSON.parse(localStorage.getItem(FAVOURITES) ?? '[]') as string[]
  } catch {
    return []
  }
}

function Avatar({ id, name, small }: { id: string; name: string; small?: boolean }) {
  return (
    <span className={`avatar avatar--t${tone(id)}${small ? ' avatar--sm' : ''}`} aria-hidden="true">
      {initials(name)}
    </span>
  )
}

function PostCard({
  post,
  community,
  persona,
  startOpen,
  onChange,
}: {
  post: Post
  community: Community | undefined
  persona: string
  startOpen: boolean
  onChange: (post: Post) => void
}) {
  const [open, setOpen] = useState(startOpen)
  const [thread, setThread] = useState<Thread | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const card = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!open || thread) return
    const ctrl = new AbortController()
    fetchThread(post.thread_id, persona, ctrl.signal)
      .then(setThread)
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Could not load the replies.')
      })
    return () => ctrl.abort()
  }, [open, thread, post.thread_id, persona])

  useEffect(() => {
    if (startOpen) card.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [startOpen])

  async function like() {
    setError('')
    try {
      onChange(await setLike(post.id, !post.liked_by_me, persona))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your like.')
    }
  }

  async function reply(e: FormEvent) {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return
    setBusy(true)
    setError('')
    try {
      const made = await postReply(post.thread_id, text, persona)
      setThread((t) => (t ? { ...t, replies: [...t.replies, made] } : t))
      onChange({ ...post, reply_count: post.reply_count + 1 })
      setDraft('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Your reply was not posted.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article ref={card} className={`post${open ? ' post--open' : ''}`} aria-labelledby={`post-${post.id}`}>
      <header className="post__head">
        <Avatar id={post.author.id} name={post.author.name} />
        <div className="post__who">
          <span className="post__name" id={`post-${post.id}`}>
            {post.author.name}
          </span>
          <span className="post__sub">
            {post.author.title && <>{post.author.title} · </>}
            {community ? (
              <Link to={`/community?c=${encodeURIComponent(community.id)}`} className="post__community">
                {community.name}
              </Link>
            ) : null}
            {community && ' · '}
            <time dateTime={post.created_at}>{timeAgo(post.created_at)}</time>
          </span>
        </div>
        {KIND_LABEL[post.kind] && <span className={`kind kind--${post.kind}`}>{KIND_LABEL[post.kind]}</span>}
      </header>
      {post.title && <h3 className="post__title">{post.title}</h3>}
      <p className="post__body">{post.body}</p>
      {post.topics.length > 0 && (
        <div className="post__topics">
          {post.topics.map((t) => (
            <span key={t} className="chip">
              {t}
            </span>
          ))}
        </div>
      )}
      <footer className="post__actions">
        <button
          type="button"
          className={`post__act${post.liked_by_me ? ' is-on' : ''}`}
          aria-pressed={post.liked_by_me}
          onClick={() => void like()}
        >
          <ThumbsUp size={16} strokeWidth={2.2} /> Like{post.like_count ? ` · ${post.like_count}` : ''}
        </button>
        <button type="button" className="post__act" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <MessageSquare size={16} strokeWidth={2.2} /> {post.reply_count ? `${post.reply_count} ${post.reply_count === 1 ? 'reply' : 'replies'}` : 'Reply'}
        </button>
        {post.web_url && (
          <a className="post__act post__act--end" href={post.web_url} target="_blank" rel="noreferrer">
            Open in Viva Engage <ExternalLink size={13} strokeWidth={2.2} />
          </a>
        )}
      </footer>
      {error && !open && (
        <p className="post__error" role="alert">
          {error}
        </p>
      )}
      {open && (
        <div className="post__thread">
          {!thread ? (
            <div className="skeleton" style={{ height: 56 }} />
          ) : (
            <ul className="replies">
              {thread.replies.map((r) => (
                <li key={r.id} className="reply">
                  <Avatar id={r.author.id} name={r.author.name} small />
                  <div className="reply__bubble">
                    <span className="reply__who">
                      {r.author.name}
                      {r.author.title && <span className="reply__title"> · {r.author.title}</span>}
                      <span className="reply__time"> · {timeAgo(r.created_at)}</span>
                    </span>
                    <span className="reply__body">{r.body}</span>
                    {r.local && <span className="reply__local">Saved in the hub only</span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <form className="replyform" onSubmit={(e) => void reply(e)}>
            <textarea
              rows={2}
              value={draft}
              maxLength={2000}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Write a reply. No client names, account numbers or other client data."
              aria-label={`Reply to ${post.author.name}`}
            />
            <button className="btn btn--inline" disabled={busy || !draft.trim()}>
              {busy ? 'Posting…' : 'Reply'}
            </button>
          </form>
          {error && (
            <p className="post__error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </article>
  )
}

export function CommunityPage() {
  const { persona } = usePersona()
  const { pathname } = useLocation()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const view = pathname.split('/')[2] ?? ''
  const meta = VIEWS[view] ?? VIEWS['']
  const selected = params.get('c') ?? ''
  const directory = params.get('view') === 'directory'
  const q = params.get('q') ?? ''
  const openThread = params.get('thread') ?? ''

  const [home, setHome] = useState<CommunityHome | null>(null)
  const [feed, setFeed] = useState<{ key: string; feed: Feed } | null>(null)
  const [learning, setLearning] = useState<Item[]>([])
  const [error, setError] = useState('')
  const [draft, setDraft] = useState(q)
  const [favourites, setFavourites] = useState<string[]>(readFavourites)
  const [course, setCourse] = useState<string | null>(null)
  useEffect(() => setDraft(q), [q])

  useEffect(() => {
    const ctrl = new AbortController()
    fetchCommunityHome(persona, ctrl.signal)
      .then(setHome)
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Community is unavailable.')
      })
    Promise.all(['Microsoft Learn', 'Pluralsight'].map((source) => fetchItems({ source, persona }, ctrl.signal)))
      .then((lists) => setLearning(lists.flatMap((l) => l.filter((i) => i.personas.includes(persona)).slice(0, 2))))
      .catch(() => setLearning([]))
    return () => ctrl.abort()
  }, [persona])

  const key = [persona, selected, meta.kind ?? '', q].join('|')
  useEffect(() => {
    if (view === 'experts' || directory) return
    const ctrl = new AbortController()
    fetchFeed({ community: selected || undefined, kind: meta.kind ?? '', q, persona }, ctrl.signal)
      .then((found) => setFeed({ key, feed: found }))
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Could not load posts.')
      })
    return () => ctrl.abort()
  }, [key, selected, meta.kind, q, persona, view, directory])

  const byId = useMemo(() => new Map((home?.communities ?? []).map((c) => [c.id, c])), [home])
  const community = selected ? byId.get(selected) : undefined
  const current = feed?.key === key ? feed.feed : null
  const connection = current?.connection ?? home?.connection
  const live = connection?.source === 'viva_engage'

  const toggleFavourite = useCallback((id: string) => {
    setFavourites((prev) => {
      const next = prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
      try {
        localStorage.setItem(FAVOURITES, JSON.stringify(next))
      } catch {
        /* storage may be unavailable; favourites then last this visit */
      }
      return next
    })
  }, [])

  function search(e: FormEvent) {
    e.preventDefault()
    const next = new URLSearchParams(params)
    if (draft.trim()) next.set('q', draft.trim())
    else next.delete('q')
    next.delete('thread')
    setParams(next, { replace: true })
  }

  function update(post: Post) {
    setFeed((f) => (f ? { ...f, feed: { ...f.feed, posts: f.feed.posts.map((p) => (p.id === post.id ? post : p)) } } : f))
  }

  const title = directory ? 'Communities' : community ? community.name : meta.title
  const mine = (home?.mine ?? []).map((id) => byId.get(id)).filter(Boolean) as Community[]
  const favouriteCommunities = favourites.map((id) => byId.get(id)).filter(Boolean) as Community[]

  return (
    <div className="content content--wide">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} strokeWidth={2.2} />
        <Link to="/community">Community</Link>
        {title !== 'Home' && (
          <>
            <ChevronRight size={16} strokeWidth={2.2} />
            <span>{title}</span>
          </>
        )}
      </nav>

      <div className="cm">
        <aside className="cm-nav" aria-label="Community">
          <nav className="cm-nav__group">
            {Object.entries(VIEWS).map(([id, v]) => {
              const Icon = v.icon
              const active = !directory && !selected && view === id
              return (
                <Link key={id || 'home'} to={`/community${id ? '/' + id : ''}`} className={`cm-nav__item${active ? ' is-active' : ''}`}>
                  <Icon size={17} strokeWidth={2} /> {v.title}
                </Link>
              )
            })}
            <Link to="/community?view=directory" className={`cm-nav__item${directory ? ' is-active' : ''}`}>
              <Compass size={17} strokeWidth={2} /> Explore communities
            </Link>
          </nav>

          <div className="cm-nav__label">Favourites</div>
          {favouriteCommunities.length ? (
            <nav className="cm-nav__group">
              {favouriteCommunities.map((c) => (
                <Link key={c.id} to={`/community?c=${encodeURIComponent(c.id)}`} className={`cm-nav__item${selected === c.id ? ' is-active' : ''}`}>
                  <Star size={15} strokeWidth={2} className="cm-star is-on" /> {c.name}
                </Link>
              ))}
            </nav>
          ) : (
            <p className="cm-nav__hint">Star a community and it shows up here.</p>
          )}

          <div className="cm-nav__label">Your communities</div>
          <nav className="cm-nav__group">
            {mine.map((c) => (
              <Link key={c.id} to={`/community?c=${encodeURIComponent(c.id)}`} className={`cm-nav__item${selected === c.id ? ' is-active' : ''}`}>
                <span className="cm-dot" aria-hidden="true">
                  {initials(c.name)}
                </span>
                <span className="cm-nav__name">{c.name}</span>
                {c.privacy === 'private' && <Lock size={13} strokeWidth={2.2} aria-label="Private" />}
              </Link>
            ))}
          </nav>
          <Link to="/community?view=directory" className="textlink cm-nav__more">
            Discover communities
          </Link>
        </aside>

        <main className="cm-main">
          <section className="cm-head">
            <div className="cm-head__top">
              <div>
                <h1 className="cm-head__title">{title}</h1>
                <p className="cm-head__lead">
                  {community
                    ? community.description
                    : directory
                      ? 'Every community you can see. Open one to read and join the conversation.'
                      : view === 'experts'
                        ? 'Colleagues who answer questions in these communities.'
                        : 'Conversations from the communities you can see, newest first.'}
                </p>
                {community && (
                  <p className="cm-head__facts">
                    {community.member_count !== null && <span>{community.member_count.toLocaleString()} members</span>}
                    <span>{community.privacy === 'private' ? 'Private' : 'Public'}</span>
                  </p>
                )}
              </div>
              {community && (
                <button
                  type="button"
                  className={`btn-outline${favourites.includes(community.id) ? ' is-on' : ''}`}
                  aria-pressed={favourites.includes(community.id)}
                  onClick={() => toggleFavourite(community.id)}
                >
                  <Star size={15} strokeWidth={2.2} className={`cm-star${favourites.includes(community.id) ? ' is-on' : ''}`} />{' '}
                  {favourites.includes(community.id) ? 'Favourite' : 'Add to favourites'}
                </button>
              )}
            </div>
            {!directory && view !== 'experts' && (
              <form className="cm-search" onSubmit={search} role="search">
                <Search size={16} strokeWidth={2.2} aria-hidden="true" />
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={`Search ${community ? community.name : 'Community'}`}
                  aria-label="Search posts"
                />
              </form>
            )}
          </section>

          {connection && (
            <div className={`cm-source${live ? ' cm-source--live' : ''}`} role="status">
              <ShieldCheck size={16} strokeWidth={2.2} />
              <span>{live ? 'Live from Viva Engage, with your permissions.' : connection.notice}</span>
              <Link to="/integrations" className="textlink">
                {live ? 'Integrations' : 'What is needed to go live'}
              </Link>
            </div>
          )}

          {error && (
            <div className="state state--error" role="alert">
              {error}
            </div>
          )}

          {directory ? (
            <div className="cm-grid">
              {(home?.communities ?? []).map((c) => (
                <article key={c.id} className="cm-card cm-card--cover">
                  <Cover
                    icon={subjectIcon(`${c.name} ${c.topics.join(' ')}`, Users)}
                    tone={toneFor(c.id)}
                    label={c.privacy === 'private' ? 'Private' : 'Public'}
                    size="compact"
                  />
                  <h2 className="cm-card__title">{c.name}</h2>
                  <p className="cm-card__text">{c.description}</p>
                  <p className="cm-card__facts">
                    {c.member_count !== null && <span>{c.member_count.toLocaleString()} members</span>}
                    <span>{c.privacy === 'private' ? 'Private' : 'Public'}</span>
                  </p>
                  <button type="button" className="btn-outline" onClick={() => navigate(`/community?c=${encodeURIComponent(c.id)}`)}>
                    Open
                  </button>
                </article>
              ))}
            </div>
          ) : view === 'experts' ? (
            <div className="cm-grid">
              {(home?.experts ?? []).map((e) => (
                <article key={e.person.id} className="cm-card">
                  <Avatar id={e.person.id} name={e.person.name} />
                  <h2 className="cm-card__title">{e.person.name}</h2>
                  <p className="cm-card__text">{e.person.title}</p>
                  <div className="post__topics">
                    {e.topics.map((t) => (
                      <span key={t} className="chip">
                        {t}
                      </span>
                    ))}
                  </div>
                  <p className="cm-card__facts">
                    Answers in {e.community_ids.map((id) => byId.get(id)?.name).filter(Boolean).join(', ')}
                  </p>
                </article>
              ))}
            </div>
          ) : !current ? (
            <div className="cm-feed" aria-busy="true">
              {[0, 1, 2].map((n) => (
                <div key={n} className="skeleton" style={{ height: 150 }} />
              ))}
            </div>
          ) : current.posts.length ? (
            <div className="cm-feed">
              {current.posts.map((p) => (
                <PostCard
                  key={p.id}
                  post={p}
                  community={byId.get(p.community_id)}
                  persona={persona}
                  startOpen={openThread === p.id}
                  onChange={update}
                />
              ))}
            </div>
          ) : (
            <div className="state">{q ? `No posts match “${q}”.` : 'No posts here yet.'}</div>
          )}
        </main>

        <aside className="cm-rail" aria-label="Suggestions">
          <section className="cm-panel cm-panel--note">
            <h2 className="cm-panel__title">
              <ShieldCheck size={16} strokeWidth={2.2} /> Community guidelines
            </h2>
            <p>Everyone in a community can read its posts. Keep client names, account numbers and other client data out of posts and replies.</p>
          </section>

          {(home?.suggested.length ?? 0) > 0 && (
            <section className="cm-panel">
              <h2 className="cm-panel__title">Suggested communities</h2>
              <ul className="cm-list">
                {home!.suggested.map((c) => (
                  <li key={c.id}>
                    <Link to={`/community?c=${encodeURIComponent(c.id)}`} className="cm-list__row">
                      <span className="cm-dot" aria-hidden="true">
                        {initials(c.name)}
                      </span>
                      <span>
                        <span className="cm-list__name">{c.name}</span>
                        {c.member_count !== null && <span className="cm-list__sub">{c.member_count.toLocaleString()} members</span>}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <Link to="/community?view=directory" className="textlink">
                Discover more
              </Link>
            </section>
          )}

          {learning.length > 0 && (
            <section className="cm-panel">
              <h2 className="cm-panel__title">Learning for your role</h2>
              <div className="cm-learning">
                {learning.map((i) => (
                  <CourseCard key={i.id} item={i} onOpen={setCourse} />
                ))}
              </div>
              <Link to="/learning" className="textlink">
                All learning
              </Link>
            </section>
          )}

          {(home?.experts.length ?? 0) > 0 && (
            <section className="cm-panel">
              <h2 className="cm-panel__title">Experts to follow</h2>
              <ul className="cm-list">
                {home!.experts.slice(0, 3).map((e) => (
                  <li key={e.person.id} className="cm-list__row">
                    <Avatar id={e.person.id} name={e.person.name} small />
                    <span>
                      <span className="cm-list__name">{e.person.name}</span>
                      <span className="cm-list__sub">{e.topics.join(', ')}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <Link to="/community/experts" className="textlink">
                SME directory
              </Link>
            </section>
          )}
        </aside>
      </div>
      <CourseDrawer itemId={course} onClose={() => setCourse(null)} />
    </div>
  )
}
