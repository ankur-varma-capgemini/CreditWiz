import { Bookmark, BookmarkCheck, Clock, Sparkles, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import { RELATION_LABEL, type PromptCard, type Risk } from '../../lib/prompts'
import { subjectIcon } from '../../lib/visuals'
import { Cover } from '../Cover'

export function RiskPill({ risk }: { risk: Risk }) {
  return <span className={`risk risk--${risk.toLowerCase()}`}>{risk} risk</span>
}

export function formatCount(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1).replace('.0', '')}k` : String(n)
}

/** One prompt in a grid. The whole card opens it; the bookmark saves it. */
export function PromptTile({ p, onToggleSave }: { p: PromptCard; onToggleSave?: (p: PromptCard) => void }) {
  return (
    <article className="ptile">
      <div className="card-head">
        <Cover icon={subjectIcon(p.category, Sparkles)} size="tile" />
        <div className="ptile__top">
          <span className="ptile__cat">{p.category}</span>
          <RiskPill risk={p.risk} />
        </div>
      </div>
      <h3 className="ptile__title">
        <Link to={`/library/prompts/${p.id}`}>{p.title}</Link>
      </h3>
      <p className="ptile__desc">{p.description}</p>
      <ul className="ptile__tags" aria-label="Tags">
        {p.tags.slice(0, 3).map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <div className="ptile__meta">
        <span>
          <Star className="star" size={13} strokeWidth={2.4} aria-hidden="true" /> {p.rating}
          <span className="muted">({p.ratings})</span>
        </span>
        <span>{formatCount(p.uses)} uses</span>
        <span>
          <Clock size={13} strokeWidth={2.4} aria-hidden="true" /> {p.hours_saved}h saved per use
        </span>
      </div>
      <div className="ptile__foot">
        <span className="ptile__who">
          <span className="pavatar" aria-hidden="true">
            {p.contributor.initials}
          </span>
          <span className="ptile__name">
            {p.contributor.name}
            <span className="muted"> · {p.relation === 'other' ? p.desk.label : RELATION_LABEL[p.relation]}</span>
          </span>
        </span>
        {onToggleSave && (
          <button
            type="button"
            className="savebtn"
            aria-pressed={p.saved}
            aria-label={p.saved ? `Remove ${p.title} from My library` : `Save ${p.title} to My library`}
            onClick={() => onToggleSave(p)}
          >
            {p.saved ? <BookmarkCheck size={16} strokeWidth={2.2} /> : <Bookmark size={16} strokeWidth={2.2} />}
          </button>
        )}
      </div>
    </article>
  )
}
