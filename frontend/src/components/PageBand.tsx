import type { ReactNode } from 'react'

interface Props {
  title: ReactNode
  lead?: ReactNode
  /** Right-hand slot: filters, actions, status. */
  aside?: ReactNode
  /** Row under the lead: search, tabs, chips. */
  children?: ReactNode
  /** Less vertical padding, for pages where content is the point. */
  compact?: boolean
  /** Short label above the title, such as the section it belongs to. */
  kicker?: ReactNode
}

/**
 * The light header every page opens with. One consistent anchor across Nexus:
 * kicker, title, lead, an optional control row and an optional right-hand slot.
 */
export function PageBand({ title, lead, aside, children, compact, kicker }: Props) {
  return (
    <div className={`band${compact ? ' band--compact' : ''}`}>
      <div className="band__inner">
        <div className="band__text">
          {kicker && <div className="band__kicker">{kicker}</div>}
          <h1 className="band__title">{title}</h1>
          {lead && <p className="band__lead">{lead}</p>}
        </div>
        {aside && <div className="band__aside">{aside}</div>}
      </div>
      {children}
    </div>
  )
}
