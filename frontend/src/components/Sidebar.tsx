import { CircleHelp, Home, Plug, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { PillarGlyph } from '../lib/icons'
import { pillarBasePath, type Pillar } from '../lib/types'

interface Props {
  pillars: Pillar[]
  /** Below the desktop breakpoint the sidebar is an off-canvas drawer. */
  open?: boolean
  onClose?: () => void
}

function cls(base: string) {
  return ({ isActive }: { isActive: boolean }) => (isActive ? `${base} is-active` : base)
}

/**
 * Official logo: drop the brand file at frontend/public/mufg-logo.svg (or .png and
 * change the path below). Until that file exists the drawn mark + wordmark is shown.
 */
const LOGO_SRC = '/mufg-logo.svg'

function MufgLogo() {
  const [failed, setFailed] = useState(false)
  if (!failed) {
    return <img className="brand__img" src={LOGO_SRC} alt="MUFG" onError={() => setFailed(true)} />
  }
  return (
    <>
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <circle cx="20" cy="20" r="18" fill="#e60000" />
        <circle cx="20" cy="20" r="9.5" fill="#fff" />
        <circle cx="20" cy="20" r="5.5" fill="#e60000" />
      </svg>
      <span>MUFG</span>
    </>
  )
}

export function Sidebar({ pillars, open = false, onClose }: Props) {
  // Escape closes the drawer, the same as tapping the scrim.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {open && <button type="button" className="scrim" aria-label="Close menu" onClick={onClose} />}
      <aside className={`sidebar${open ? ' sidebar--open' : ''}`} aria-label="Primary">
      <NavLink to="/" className="brand" aria-label="MUFG AI Hub home">
        <div className="brand__logo">
          <MufgLogo />
        </div>
        <div className="brand__product">
          <div className="brand__wordmark">MUFG AI Hub</div>
          <div className="brand__tagline">Enterprise · Americas</div>
        </div>
      </NavLink>

      <nav className="nav">
        <NavLink to="/" end className={cls('nav__item nav__item--home')}>
          <Home className="nav__icon" strokeWidth={2.2} />
          <span className="nav__label">Home</span>
        </NavLink>
        {/* The Super Agent: one conversation across every pillar, on a page of its own. */}
        <NavLink to="/super-agent" className={cls('nav__item nav__item--home')}>
          <Sparkles className="nav__icon" strokeWidth={2.2} />
          <span className="nav__label">Super Agent</span>
        </NavLink>

        <div className="nav__section">Workspace</div>

        {pillars.map((p) => (
          <NavLink key={p.id} to={pillarBasePath(p)} className={cls('nav__item')}>
            <PillarGlyph icon={p.icon} className="nav__icon" strokeWidth={2} />
            <span className="nav__label">{p.short_title}</span>
          </NavLink>
        ))}

        <div className="nav__spacer" />
        <div className="nav__divider" />

        <NavLink to="/integrations" className={cls('nav__item nav__item--util')}>
          <Plug className="nav__icon" strokeWidth={2} />
          <span className="nav__label">Integrations</span>
        </NavLink>
        <NavLink to="/help" className={cls('nav__item nav__item--util')}>
          <CircleHelp className="nav__icon" strokeWidth={2} />
          <span className="nav__label">Help &amp; support</span>
        </NavLink>
      </nav>
      </aside>
    </>
  )
}
