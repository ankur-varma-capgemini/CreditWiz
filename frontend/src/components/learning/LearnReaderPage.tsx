import { ArrowLeft, ArrowRight, Check, ChevronRight, Clock, ExternalLink, Layers } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { fetchLearnPage, readerHref, recordProgress, type LearnPage } from '../../lib/learning'
import { Markdown } from '../Markdown'

const LEARN = /(?<!!)\[([^\]]*)\]\((https:\/\/learn\.microsoft\.com\/[^)\s]+)\)/g

/** A unit's module is the folder it sits in. */
function moduleOf(url: string) {
  return url.replace(/\/[^/]+$/, '/')
}

/**
 * A Microsoft Learn page, read in the hub through Microsoft's Learn MCP server.
 * Links to other Learn pages stay in the hub; everything else opens in a new tab.
 */
export function LearnReaderPage() {
  const [params] = useSearchParams()
  const url = params.get('url') ?? ''
  const itemId = params.get('item') ?? ''
  const [page, setPage] = useState<{ url: string; page: LearnPage } | null>(null)
  const [parent, setParent] = useState<LearnPage | null>(null)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!url) return
    const ctrl = new AbortController()
    setError('')
    setParent(null)
    fetchLearnPage(url, ctrl.signal)
      .then((found) => {
        setPage({ url, page: found })
        if (found.kind === 'Unit') {
          fetchLearnPage(moduleOf(url), ctrl.signal)
            .then(setParent)
            .catch(() => setParent(null))
        }
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(e instanceof Error ? e.message : 'Microsoft Learn did not answer.')
      })
    window.scrollTo({ top: 0 })
    return () => ctrl.abort()
  }, [url])

  const current = page?.url === url ? page.page : null
  const units = current?.kind === 'Unit' ? (parent?.units ?? []) : (current?.units ?? [])
  const at = units.findIndex((u) => u.url === url)
  const prev = at > 0 ? units[at - 1] : null
  const next = at >= 0 && at < units.length - 1 ? units[at + 1] : current?.kind === 'Module' ? units[0] : null
  const body = current ? current.markdown.replace(LEARN, (_, text: string, href: string) => `[${text}](${readerHref(href, itemId)})`) : ''

  return (
    <div className="content reader">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <ChevronRight size={16} />
        <Link to="/learning">Learning</Link>
        <ChevronRight size={16} />
        {current?.kind === 'Unit' && parent ? <Link to={readerHref(moduleOf(url), itemId)}>{parent.title}</Link> : <span>Microsoft Learn</span>}
        {current && (
          <>
            <ChevronRight size={16} />
            <span>{current.title}</span>
          </>
        )}
      </nav>

      {!url ? (
        <div className="state">Choose a Microsoft Learn page to read.</div>
      ) : error ? (
        <div className="state state--error" role="alert">
          {error}{' '}
          <a href={url} target="_blank" rel="noreferrer">
            Open it on Microsoft Learn
          </a>
        </div>
      ) : !current ? (
        <div aria-busy="true">
          <div className="skeleton" style={{ height: 40, width: '60%', marginBottom: 16 }} />
          <div className="skeleton" style={{ height: 320 }} />
        </div>
      ) : (
        <div className="reader__grid">
          <article className="reader__main">
            <header className="reader__head">
              <span className="provider provider--mslearn">Microsoft Learn</span>
              <h1 className="reader__title">{current.title}</h1>
              <p className="drawer__meta">
                <span>{current.kind}</span>
                {current.level && <span>{current.level}</span>}
                {current.count && (
                  <span>
                    <Layers size={14} strokeWidth={2.2} /> {current.count}
                  </span>
                )}
                {current.minutes && (
                  <span>
                    <Clock size={14} strokeWidth={2.2} /> {current.minutes} min
                  </span>
                )}
              </p>
            </header>
            <Markdown source={body} />
            <nav className="reader__pager" aria-label="Units">
              {prev ? (
                <Link className="btn-outline" to={readerHref(prev.url, itemId)}>
                  <ArrowLeft size={14} strokeWidth={2.4} /> {prev.title}
                </Link>
              ) : (
                <span />
              )}
              {next && (
                <Link className="btn btn--inline" to={readerHref(next.url, itemId)}>
                  {current.kind === 'Module' ? 'Start' : 'Next'}: {next.title} <ArrowRight size={14} strokeWidth={2.4} />
                </Link>
              )}
            </nav>
            <p className="reader__credit">
              Content from Microsoft Learn, read through Microsoft's Learn MCP server.{' '}
              <a href={url} target="_blank" rel="noreferrer">
                Open the original <ExternalLink size={12} strokeWidth={2.4} />
              </a>
            </p>
          </article>

          <aside className="reader__side">
            {units.length > 0 && (
              <section className="panel">
                <h2 className="panel__title">{(current.kind === 'Unit' ? parent?.kind : current.kind) === 'Learning path' ? 'Modules' : 'Units'}</h2>
                <ol className="drawer__units">
                  {units.map((u) => (
                    <li key={u.url} className={u.url === url ? 'is-current' : ''}>
                      <Link to={readerHref(u.url, itemId)} aria-current={u.url === url ? 'page' : undefined}>
                        {u.title}
                      </Link>
                    </li>
                  ))}
                </ol>
              </section>
            )}
            {itemId && (
              <section className="panel">
                <h2 className="panel__title">Your progress</h2>
                <p className="panel__text">Mark the course complete when you have read it all.</p>
                <button
                  type="button"
                  className="btn-outline"
                  disabled={done}
                  onClick={() => void recordProgress(itemId, 'completed', 100).then(() => setDone(true))}
                >
                  <Check size={14} strokeWidth={2.6} /> {done ? 'Marked complete' : 'Mark complete'}
                </button>
              </section>
            )}
          </aside>
        </div>
      )}
    </div>
  )
}
