import { Preferences } from './Preferences'
import { ArrowRight, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useHub } from '../lib/hub'
import { PageBand } from './PageBand'

function Crumbs({ title }: { title: string }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <Link to="/">Home</Link>
      <ChevronRight size={16} strokeWidth={2.2} />
      <span>{title}</span>
    </nav>
  )
}

export function HelpPage() {
  return (
    <div className="content">
      <Crumbs title="Help" />
      <PageBand title="Help &amp; support" lead="Browse the getting-started path, agent documentation, and learning catalog." compact />
      <section className="more-grid">
        <Link to="/learning?path=getting-started" className="scard scard--teal">
          <span className="scard__title">Getting started</span>
          <span className="scard__blurb">Your first hour with AI at MUFG.</span>
          <span className="scard__go">
            Open <ArrowRight size={18} strokeWidth={2.4} />
          </span>
        </Link>
        <Link to="/learning/catalog" className="scard scard--blue">
          <span className="scard__title">Learning catalog</span>
          <span className="scard__blurb">Find guides, quick references, courses, and videos.</span>
          <span className="scard__go">
            Open <ArrowRight size={18} strokeWidth={2.4} />
          </span>
        </Link>
        <Link to="/marketplace/agents" className="scard scard--blue">
          <span className="scard__title">Agent documentation</span>
          <span className="scard__blurb">Open an agent to read its documentation and contact details.</span>
          <span className="scard__go">
            Open <ArrowRight size={18} strokeWidth={2.4} />
          </span>
        </Link>
      </section>
    </div>
  )
}

export function SettingsPage() {
  const { user } = useHub()
  return (
    <div className="content">
      <Crumbs title="Profile" />
      <PageBand
        kicker={user.job_title}
        title={user.display_name}
        lead="Your directory profile, the persona Nexus derives from it, and your preferences."
        aside={<span className="band__count">{user.persona.label}</span>}
        compact
      />

      <section className="panel">
        <h2 className="panel__title">Profile</h2>
        <dl className="kv">
          <dt>Name</dt>
          <dd>{user.display_name}</dd>
          <dt>Job title</dt>
          <dd>{user.job_title}</dd>
          <dt>Department</dt>
          <dd>{user.department}</dd>
          <dt>Business unit</dt>
          <dd>{user.business_unit}</dd>
          <dt>Location</dt>
          <dd>{user.location}</dd>
          <dt>Manager</dt>
          <dd>{user.manager}</dd>
          <dt>Nexus access</dt>
          <dd>{user.is_admin ? 'Hub administrator' : 'Employee'}</dd>
          <dt>Employee ID</dt>
          <dd>{user.id}</dd>
        </dl>
      </section>

      <section className="panel">
        <h2 className="panel__title">Persona</h2>
        <p className="panel__text">
          <strong>{user.persona.label}</strong>. Derived by Nexus from your directory profile ({user.persona.rule}); it is not stored on
          your profile. It shapes which agents and learning are recommended to you.
        </p>
      </section>

      <Preferences />
    </div>
  )
}

export function NotFound() {
  return (
    <div className="content">
      <Crumbs title="Not found" />
      <PageBand title="We couldn't find that page" lead="The link may be out of date, or you may not have access to it." compact />
      <Link className="mcard__link" to="/">
        Back to home <ArrowRight strokeWidth={2.4} />
      </Link>
    </div>
  )
}
