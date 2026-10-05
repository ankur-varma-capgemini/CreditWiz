import { BookOpen, Check, Clock, ExternalLink, GraduationCap, Layers, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import {
  duration,
  fetchItem,
  fetchLearnPage,
  itemHref,
  readerHref,
  recordProgress,
  TYPE_LABEL,
  type ItemDetail,
  type LearnPage,
} from '../../lib/learning'

/**
 * A course's details in a side panel, so browsing never leaves the page.
 *
 * Pluralsight plays its videos only on its own site, so Start opens Pluralsight
 * in a new tab. Microsoft Learn reads inside the hub, and its units and
 * objectives come live from Microsoft Learn.
 */
export function CourseDrawer({ itemId, onClose }: { itemId: string | null; onClose: () => void }) {
  const [item, setItem] = useState<ItemDetail | null>(null)
  const [learn, setLearn] = useState<LearnPage | null>(null)
  const [learnError, setLearnError] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const close = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!itemId) return
    const ctrl = new AbortController()
    setItem(null)
    setLearn(null)
    setLearnError('')
    setError('')
    fetchItem(itemId, ctrl.signal)
      .then((found) => {
        setItem(found)
        if (found.read_in_hub && found.url) {
          fetchLearnPage(found.url, ctrl.signal)
            .then(setLearn)
            .catch((e: unknown) => {
              if (!isAbort(e)) setLearnError(e instanceof Error ? e.message : 'Microsoft Learn did not answer.')
            })
        }
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Could not load this course.')
      })
    return () => ctrl.abort()
  }, [itemId])

  useEffect(() => {
    if (!itemId) return
    close.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [itemId, onClose])

  if (!itemId) return null

  async function mark(status: 'in_progress' | 'completed') {
    if (!item) return
    setBusy(true)
    try {
      const updated = await recordProgress(item.id, status, status === 'completed' ? 100 : undefined)
      setItem({ ...item, status: updated.status, progress: updated.progress })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your progress.')
    } finally {
      setBusy(false)
    }
  }

  const pluralsight = item?.source === 'Pluralsight'
  const learnItem = !!item?.read_in_hub
  const started = item && item.status !== 'not_started'
  const searchOnly = pluralsight && !item?.live && (item?.launch_url ?? '').startsWith('https://www.pluralsight.com/search')
  const objectives = learn?.objectives.length ? learn.objectives : (item?.outcomes ?? [])
  const time = item ? duration(item.duration_seconds) : ''

  // Rendered at the document root: the page's entrance animation makes its
  // content a containing block, which would trap a fixed panel inside it.
  return createPortal(
    <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <button type="button" className="drawer__scrim" aria-label="Close course details" onClick={onClose} />
      <aside className="drawer__panel">
        <header className="drawer__head">
          <span className={`provider provider--${pluralsight ? 'pluralsight' : learnItem ? 'mslearn' : 'hub'}`}>
            {item?.source || 'Course'}
          </span>
          {item?.live && <span className="status">Live</span>}
          {item && !item.live && pluralsight && <span className="status status--deprecated">Sample catalogue</span>}
          <button ref={close} type="button" className="drawer__close" aria-label="Close" onClick={onClose}>
            <X size={18} strokeWidth={2.2} />
          </button>
        </header>

        {error ? (
          <p className="drawer__error" role="alert">
            {error}
          </p>
        ) : !item ? (
          <div className="drawer__body" aria-busy="true">
            <div className="skeleton" style={{ height: 28, width: '80%', marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 16, width: '50%', marginBottom: 24 }} />
            <div className="skeleton" style={{ height: 120 }} />
          </div>
        ) : (
          <div className="drawer__body">
            <h2 className="drawer__title" id="drawer-title">
              {item.title}
            </h2>
            <p className="drawer__meta">
              <span>
                <GraduationCap size={14} strokeWidth={2.2} /> {learn?.kind ?? TYPE_LABEL[item.type]}
              </span>
              {(learn?.level || item.level) && <span>{learn?.level || item.level}</span>}
              {time && (
                <span>
                  <Clock size={14} strokeWidth={2.2} /> {time}
                </span>
              )}
              {learn?.count && (
                <span>
                  <Layers size={14} strokeWidth={2.2} /> {learn.count}
                </span>
              )}
              {item.instructor && <span>By {item.instructor}</span>}
            </p>

            {item.recommendation_reason && (
              <p className="drawer__why">
                <span className="drawer__why-label">Why it's recommended</span>
                {item.recommendation_reason}
              </p>
            )}

            {started && (
              <div className="drawer__progress" aria-label={`${item.progress}% complete`}>
                <span className="drawer__bar">
                  <span style={{ width: `${item.status === 'completed' ? 100 : item.progress}%` }} />
                </span>
                <span>{item.status === 'completed' ? 'Completed' : item.progress ? `${item.progress}% complete` : 'Started'}</span>
              </div>
            )}

            <div className="drawer__actions">
              {learnItem ? (
                <>
                  <Link className="btn btn--inline" to={readerHref(item.url, item.id)} onClick={() => !started && void mark('in_progress')}>
                    <BookOpen size={16} strokeWidth={2.2} /> {started ? 'Continue reading' : 'Read in the hub'}
                  </Link>
                  <a className="btn-outline" href={item.url} target="_blank" rel="noreferrer">
                    Open on Microsoft Learn <ExternalLink size={14} strokeWidth={2.2} />
                  </a>
                </>
              ) : item.launch_url ? (
                <a
                  className="btn btn--inline"
                  href={item.launch_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => !started && void mark('in_progress')}
                >
                  {searchOnly ? 'Find in Pluralsight' : started ? 'Continue in Pluralsight' : 'Start in Pluralsight'}{' '}
                  <ExternalLink size={14} strokeWidth={2.2} />
                </a>
              ) : null}
              {item.status !== 'completed' && (
                <button type="button" className="btn-outline" disabled={busy} onClick={() => void mark('completed')}>
                  <Check size={14} strokeWidth={2.6} /> Mark complete
                </button>
              )}
            </div>
            {pluralsight && (
              <p className="drawer__note">
                {searchOnly
                  ? 'Sample course: this opens a Pluralsight search for its title until Pluralsight is connected.'
                  : 'Pluralsight plays its videos on its own site, so the course opens in a new tab, signed in through MUFG.'}
              </p>
            )}

            <h3 className="drawer__h">About</h3>
            <p className="drawer__text">{learn?.summary || item.description}</p>

            {objectives.length > 0 && (
              <>
                <h3 className="drawer__h">What you'll learn</h3>
                <ul className="drawer__list">
                  {objectives.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
              </>
            )}

            {learnItem && (
              <>
                <h3 className="drawer__h">{learn?.kind === 'Learning path' ? 'Modules' : 'Units'}</h3>
                {learnError ? (
                  <p className="muted">{learnError}</p>
                ) : !learn ? (
                  <div className="skeleton" style={{ height: 96 }} />
                ) : (
                  <ol className="drawer__units">
                    {learn.units.map((u) => (
                      <li key={u.url}>
                        <Link to={readerHref(u.url, item.id)}>{u.title}</Link>
                      </li>
                    ))}
                  </ol>
                )}
                <p className="drawer__note">Live from Microsoft Learn, through Microsoft's Learn MCP server.</p>
              </>
            )}

            {!learnItem && (item.lessons?.length ?? 0) > 0 && (
              <>
                <h3 className="drawer__h">Contents</h3>
                <ol className="drawer__units">
                  {item.lessons!.map((l) => (
                    <li key={l.title}>
                      <span>{l.title}</span>
                      <span className="muted">{l.minutes} min</span>
                    </li>
                  ))}
                </ol>
              </>
            )}

            <Link className="textlink drawer__more" to={itemHref(item.id)}>
              Open the full course page
            </Link>
          </div>
        )}
      </aside>
    </div>,
    document.body,
  )
}
