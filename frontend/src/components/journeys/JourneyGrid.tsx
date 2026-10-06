import { Briefcase } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { JourneySummary } from '../../lib/journeys'
import { subjectIcon } from '../../lib/visuals'
import { Cover } from '../Cover'

/** The jobs a persona does, one card each, opening the journey. */
export function JourneyGrid({ journeys }: { journeys: JourneySummary[] }) {
  return (
    <ul className="jgrid">
      {journeys.map((j) => (
        <li key={j.id}>
          <Link className="jcard" to={`/journeys/${j.id}`}>
            <span className="card-head">
              <Cover icon={subjectIcon(j.title, Briefcase)} size="tile" />
              <span className="jcard__title">{j.title}</span>
            </span>
            <span className="jcard__summary">{j.summary}</span>
            <span className="jcard__systems">{j.systems.join(' · ')}</span>
            <span className="jcard__count">{j.asset_count} things that help</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
