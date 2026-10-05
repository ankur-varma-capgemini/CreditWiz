import { ArrowRight, MessageSquare, ThumbsUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { fetchCommunityHome, fetchFeed, timeAgo, type Community, type Post } from '../../lib/community'
import { fetchItems, PROVIDERS, type Item } from '../../lib/learning'
import { CourseDrawer } from '../learning/CourseDrawer'
import { CourseCard } from '../learning/ProviderShelves'
import '../../community.css'

/** What to pick up next: one course from Pluralsight or Microsoft Learn, and what your communities are discussing. */
export function ForYou({ persona }: { persona: string }) {
  const [courses, setCourses] = useState<{ continuing: boolean; items: Item[] } | null>(null)
  const [posts, setPosts] = useState<Post[] | null>(null)
  const [communities, setCommunities] = useState<Map<string, Community>>(new Map())
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    // The best course from each provider for this role: what was started first,
    // then what is mapped to the role and not yet done.
    Promise.all(PROVIDERS.map((source) => fetchItems({ source, persona }, ctrl.signal)))
      .then((lists) => {
        const ranked = lists.map((items) =>
          items
            .filter((i) => i.status === 'in_progress' || (i.status === 'not_started' && i.personas.includes(persona)))
            .sort((a, b) => Number(b.status === 'in_progress') - Number(a.status === 'in_progress')),
        )
        // One from each provider where the role has one, then the next best from either.
        const picks = ranked.map((r) => r[0]).filter((i): i is Item => !!i)
        for (const extra of ranked.flatMap((r) => r.slice(1))) {
          if (picks.length >= 2) break
          picks.push(extra)
        }
        setCourses({ continuing: picks.some((i) => i.status === 'in_progress'), items: picks })
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setCourses({ continuing: false, items: [] })
      })
    fetchFeed({ persona }, ctrl.signal)
      .then((feed) => setPosts(feed.posts.slice(0, 3)))
      .catch((e: unknown) => {
        if (!isAbort(e)) setPosts([])
      })
    fetchCommunityHome(persona, ctrl.signal)
      .then((home) => setCommunities(new Map(home.communities.map((c) => [c.id, c]))))
      .catch(() => setCommunities(new Map()))
    return () => ctrl.abort()
  }, [persona, open])

  return (
    <section className="foryou" aria-labelledby="foryou-title">
      <h2 className="home-work__title" id="foryou-title">
        For you
      </h2>
      <div className="foryou__grid">
        <div className="panel foryou__card">
          <div className="home-card__head">
            <h3 className="home-card__title">{courses?.continuing ? 'Continue learning' : 'Recommended for your role'}</h3>
            <Link to="/learning" className="textlink">
              Learning <ArrowRight size={14} strokeWidth={2.4} />
            </Link>
          </div>
          {!courses ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : courses.items.length ? (
            <div className="foryou__courses">
              {courses.items.map((i) => (
                <CourseCard key={i.id} item={i} onOpen={setOpen} />
              ))}
            </div>
          ) : (
            <p className="muted">You're up to date.</p>
          )}
        </div>

        <div className="panel foryou__card">
          <div className="home-card__head">
            <h3 className="home-card__title">From your communities</h3>
            <Link to="/community" className="textlink">
              Community <ArrowRight size={14} strokeWidth={2.4} />
            </Link>
          </div>
          {!posts ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : posts.length ? (
            <ul className="foryou__posts">
              {posts.map((p) => (
                <li key={p.id}>
                  <Link to={`/community?thread=${encodeURIComponent(p.id)}`} className="foryou__post">
                    <span className="foryou__where">
                      {communities.get(p.community_id)?.name ?? 'Community'} · {timeAgo(p.created_at)}
                    </span>
                    <span className="foryou__text">{p.title || p.body}</span>
                    <span className="foryou__stats">
                      <span>
                        <ThumbsUp size={13} strokeWidth={2.2} /> {p.like_count}
                      </span>
                      <span>
                        <MessageSquare size={13} strokeWidth={2.2} /> {p.reply_count}
                      </span>
                      <span>{p.author.name}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nothing new in your communities.</p>
          )}
        </div>
      </div>
      <CourseDrawer itemId={open} onClose={() => setOpen(null)} />
    </section>
  )
}
