import {
  BookOpen,
  Check,
  Clock,
  FileText,
  GraduationCap,
  Layers,
  Lightbulb,
  ListChecks,
  PlayCircle,
  type LucideIcon,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { TYPE_LABEL, duration, isBadge, itemHref, thumbnail, type Item, type ItemType } from '../../lib/learning'
import { Cover } from '../Cover'
import { RatingSummary } from './StarRating'

const ICON: Record<ItemType, LucideIcon> = {
  video: PlayCircle,
  course: GraduationCap,
  confluence: FileText,
  guide: BookOpen,
  documentation: Layers,
  'quick-reference': ListChecks,
  'best-practice': Lightbulb,
}

// Read rather than watched or taken: their cover is labelled with the kind of document, not a provider.
const DOCUMENT_TYPES: ReadonlySet<ItemType> = new Set(['guide', 'documentation', 'quick-reference', 'best-practice', 'confluence'])

export function ItemCard({ item, fromAgentId, compact }: { item: Item; fromAgentId?: string; compact?: boolean }) {
  const Icon = ICON[item.type] ?? BookOpen
  const isVideo = item.type === 'video'
  const isDocument = DOCUMENT_TYPES.has(item.type)
  const time = duration(item.duration_seconds)

  return (
    <Link to={itemHref(item.id, fromAgentId)} className={`icard icard--${item.type}${compact ? ' icard--compact' : ''}`}>
      <div className="card-media">
        <Cover
          icon={Icon}
          image={thumbnail(item)}
          badge={isBadge(thumbnail(item))}
          label={isDocument ? TYPE_LABEL[item.type] : item.source || TYPE_LABEL[item.type]}
          video={isVideo}
          duration={isVideo ? time : undefined}
          size={compact ? 'compact' : 'card'}
        />
        {item.status === 'in_progress' && (
          <span className="icard__bar" aria-label={`${item.progress}% complete`}>
            <span style={{ width: `${Math.max(item.progress, 4)}%` }} />
          </span>
        )}
      </div>

      <div className="icard__body">
        <span className="icard__meta">
          <span className="icard__type">{TYPE_LABEL[item.type]}</span>
          {item.required && <span className="icard__required">Required</span>}
          {item.status === 'completed' && (
            <span className="icard__done">
              <Check size={12} strokeWidth={3} /> Completed
            </span>
          )}
          {item.status === 'in_progress' && <span className="icard__pct">{item.progress ? `${item.progress}%` : 'Started'}</span>}
        </span>
        <span className="icard__title">
          {item.sequence ? `${item.sequence}. ` : ''}
          {item.title}
        </span>
        {(item.blocked_by?.length > 0 || item.prerequisite_unavailable) && <span className="icard__required">Prerequisite needed</span>}
        {item.recommendation_reason && <span className="icard__desc">{item.recommendation_reason}</span>}
        {!compact && <span className="icard__desc">{item.description}</span>}
        <span className="icard__foot">
          {!isVideo && time && (
            <span className="icard__time">
              <Clock size={12} strokeWidth={2.4} /> {time}
            </span>
          )}
          <RatingSummary average={item.rating_average} count={item.rating_count} />
        </span>
      </div>
    </Link>
  )
}
