import { ChevronRight, FileText, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { formatDate } from '../lib/format'

export interface TreePage {
  label: string
  to: string
  active?: boolean
}

interface Props {
  space: string
  crumbs: { label: string; to?: string }[]
  tree: { root: { label: string; to: string }; pages: TreePage[] }
  title: string
  status: string
  owner: string
  team: string
  updated: string
  readMinutes?: number
  properties: [string, ReactNode][]
  toc: { id: string; text: string }[]
  labels?: string[]
  /** Full width page: the page tree starts collapsed and "On this page" moves
   *  into the page, so wide content such as a diagram gets the room. */
  wide?: boolean
  children: ReactNode
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

/**
 * A documentation page laid out the way a Confluence page is: space and page
 * tree on the left, the page itself with its status, byline and page
 * properties, and an "On this page" list on the right.
 */
export function ConfluencePage(p: Props) {
  const byline = p.owner || p.team
  const [collapsed, setCollapsed] = useState(Boolean(p.wide))
  const tocInPage = Boolean(p.wide) && p.toc.length > 0
  const tocAside = !p.wide && p.toc.length > 0
  const layout = ['content', 'cf', p.wide && 'cf--wide', collapsed && 'is-collapsed', !tocAside && 'cf--no-toc']
    .filter(Boolean)
    .join(' ')

  return (
    <div className={layout}>
      {collapsed ? (
        <aside className="cf-rail" aria-label="Space">
          <button type="button" onClick={() => setCollapsed(false)} aria-label="Show page tree" title="Show page tree">
            <PanelLeftOpen size={18} strokeWidth={2} aria-hidden="true" />
            <span className="cf-rail__text">Show page tree</span>
          </button>
        </aside>
      ) : (
        <aside className="cf-space" aria-label="Space">
          <div className="cf-space__head">
            <span className="cf-space__icon" aria-hidden="true">
              AH
            </span>
            <div className="cf-space__meta">
              <p className="cf-space__name">{p.space}</p>
              <p className="cf-space__kind">Nexus space</p>
            </div>
            <button
              type="button"
              className="cf-space__toggle"
              onClick={() => setCollapsed(true)}
              aria-label="Hide page tree"
              title="Hide page tree"
            >
              <PanelLeftClose size={16} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
          <nav className="cf-tree" aria-label="Page tree">
            <p className="cf-tree__label">Pages</p>
            <ul>
              <li>
                <Link className="cf-tree__root" to={p.tree.root.to}>
                  {p.tree.root.label}
                </Link>
                <ul className="cf-tree__children">
                  {p.tree.pages.map((pg) => (
                    <li key={pg.to}>
                      <Link
                        to={pg.to}
                        className={pg.active ? 'is-active' : undefined}
                        aria-current={pg.active ? 'page' : undefined}
                      >
                        <FileText size={14} strokeWidth={2.2} aria-hidden="true" />
                        {pg.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </li>
            </ul>
          </nav>
        </aside>
      )}

      <article className="cf-page">
        <nav className="cf-crumbs" aria-label="Breadcrumb">
          {p.crumbs.map((c, i) => (
            <span key={c.label} className="cf-crumbs__item">
              {i > 0 && <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />}
              {c.to ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
            </span>
          ))}
        </nav>

        <header className="cf-head">
          <div className="cf-title-row">
            <h1 className="cf-title">{p.title}</h1>
            <span className={`cf-lozenge cf-lozenge--${p.status.toLowerCase().replace(/\s+/g, '-')}`}>{p.status}</span>
          </div>
          <div className="cf-byline">
            <span className="cf-avatar" aria-hidden="true">
              {initials(byline)}
            </span>
            <span>
              Owned by <strong>{byline}</strong>
            </span>
            <span>Last updated {formatDate(p.updated)}</span>
            {p.readMinutes ? <span>{p.readMinutes} min read</span> : null}
          </div>
        </header>

        <table className="cf-props">
          <tbody>
            {p.properties.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {tocInPage && (
          <nav className="cf-toc-inline" aria-label="On this page">
            <span className="cf-toc__title">On this page</span>
            {p.toc.map((h) => (
              <a key={h.id} href={`#${h.id}`}>
                {h.text}
              </a>
            ))}
          </nav>
        )}

        <div className="cf-body">{p.children}</div>

        {p.labels && p.labels.length > 0 && (
          <footer className="cf-labels" aria-label="Labels">
            <span className="cf-labels__title">Labels</span>
            {p.labels.map((l) => (
              <span key={l} className="cf-label">
                {l}
              </span>
            ))}
          </footer>
        )}
      </article>

      {tocAside && (
        <aside className="cf-toc" aria-label="On this page">
          <p className="cf-toc__title">On this page</p>
          <ul>
            {p.toc.map((h) => (
              <li key={h.id}>
                <a href={`#${h.id}`}>{h.text}</a>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  )
}
