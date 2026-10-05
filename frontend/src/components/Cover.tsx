import { Play, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import type { Tone } from '../lib/visuals'
import '../covers.css'

interface Props {
  icon: LucideIcon
  tone: Tone
  /** A real thumbnail. The designed cover shows when there is none, or it fails to load. */
  image?: string
  /** The image is a badge or logo, not a picture: shown on the designed cover, not filling it. */
  badge?: boolean
  /** A small label on the cover: the provider, or the kind of thing. */
  label?: string
  /** A video: a play button, and its length when known. */
  video?: boolean
  duration?: string
  /** card: 16:9 across a card's top. compact: a shorter strip. tile: a square, like an app icon. */
  size?: 'card' | 'compact' | 'tile'
}

/**
 * A thumbnail for anything in the hub. A real image when there is one; when
 * there is not, a designed cover in the thing's own colour with its icon, so
 * no card in any pillar is a grey box.
 */
export function Cover({ icon: Icon, tone, image, badge = false, label, video = false, duration, size = 'card' }: Props) {
  const [failed, setFailed] = useState(false)
  const shown = image && !failed ? image : ''
  const photo = shown && !badge
  return (
    <div className={`cover cover--${tone} cover--${size}${photo ? ' cover--photo' : ''}`} aria-hidden="true">
      {photo ? (
        <img className="cover__img" src={shown} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        <span className="cover__art">
          {shown ? (
            <img className="cover__badge" src={shown} alt="" loading="lazy" onError={() => setFailed(true)} />
          ) : (
            <Icon className="cover__icon" strokeWidth={1.8} />
          )}
        </span>
      )}
      {label && size !== 'tile' && <span className="cover__label">{label}</span>}
      {video && size !== 'tile' && (
        <span className="cover__play">
          <Play size={16} strokeWidth={2.4} fill="currentColor" />
        </span>
      )}
      {duration && size !== 'tile' && <span className="cover__time">{duration}</span>}
    </div>
  )
}
