import { BookOpen, Clock, GraduationCap, Layers } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { isAbort } from '../../lib/api'
import { fetchIntegrations, STATE_LABEL, type Integration } from '../../lib/integrations'
import { duration, fetchItems, thumbnail, type Item, type Provider } from '../../lib/learning'
import { providerTone } from '../../lib/visuals'
import { Cover } from '../Cover'
import { CourseDrawer } from './CourseDrawer'

const SHOWN = 8

/** Most relevant first: the person's role, then what they have started. */
function ranked(items: Item[], persona: string) {
  return [...items].sort(
    (a, b) =>
      Number(b.personas.includes(persona)) - Number(a.personas.includes(persona)) ||
      Number(b.status === 'in_progress') - Number(a.status === 'in_progress') ||
      a.title.localeCompare(b.title),
  )
}

export function CourseCard({ item, onOpen }: { item: Item; onOpen: (id: string) => void }) {
  const time = duration(item.duration_seconds)
  const kind = item.tags.includes('Learning path') ? 'Learning path' : item.read_in_hub ? 'Module' : 'Course'
  return (
    <button type="button" className="ccard" onClick={() => onOpen(item.id)}>
      <Cover
        icon={kind === 'Learning path' ? Layers : item.read_in_hub ? BookOpen : GraduationCap}
        tone={providerTone(item.source, item.type)}
        image={thumbnail(item)}
        badge={item.source === 'Microsoft Learn'}
        label={item.source}
        size="compact"
      />
      <span className="ccard__body">
        <span className="ccard__title">{item.title}</span>
        <span className="ccard__meta">
          <span>
            <GraduationCap size={13} strokeWidth={2.2} /> {kind}
          </span>
          {item.level && <span>{item.level}</span>}
          {time && (
            <span>
              <Clock size={13} strokeWidth={2.2} /> {time}
            </span>
          )}
          {item.read_in_hub && (
            <span>
              <BookOpen size={13} strokeWidth={2.2} /> Reads in the hub
            </span>
          )}
        </span>
        {item.status !== 'not_started' && (
          <span className="ccard__progress">
            <span className="ccard__bar">
              <span style={{ width: `${item.status === 'completed' ? 100 : Math.max(item.progress, 4)}%` }} />
            </span>
            {item.status === 'completed' ? 'Completed' : item.progress ? `${item.progress}%` : 'Started'}
          </span>
        )}
      </span>
    </button>
  )
}

function Shelf({
  provider,
  items,
  status,
  persona,
  onOpen,
}: {
  provider: Provider
  items: Item[] | null
  status: Integration | undefined
  persona: string
  onOpen: (id: string) => void
}) {
  const live = status?.state === 'live'
  return (
    <section className="shelf" aria-labelledby={`shelf-${provider}`}>
      <div className="shelf__head">
        <h2 className="shelf__title" id={`shelf-${provider}`}>
          From {provider}
        </h2>
        {status && (
          <Link to="/integrations" className={`status ${live ? '' : status.state === 'blocked' ? 'status--beta' : 'status--deprecated'}`}>
            {provider === 'Pluralsight' && !live ? (status.state === 'blocked' ? 'Blocked' : 'Sample catalogue') : STATE_LABEL[status.state]}
          </Link>
        )}
        <span className="shelf__sub">
          {provider === 'Pluralsight'
            ? 'Browse and plan here. Courses play on Pluralsight, signed in through MUFG.'
            : 'Browse and read Microsoft Learn modules right here.'}
        </span>
      </div>
      {items === null ? (
        <div className="shelf__grid">
          {[0, 1, 2, 3].map((n) => (
            <div key={n} className="skeleton" style={{ height: 132 }} />
          ))}
        </div>
      ) : items.length ? (
        <div className="shelf__grid">
          {ranked(items, persona)
            .slice(0, SHOWN)
            .map((i) => (
              <CourseCard key={i.id} item={i} onOpen={onOpen} />
            ))}
        </div>
      ) : (
        <p className="muted">Nothing from {provider} is in the catalogue for you yet.</p>
      )}
    </section>
  )
}

/**
 * Pluralsight and Microsoft Learn side by side: hub cards, details in a side
 * panel. Searching them is the Learning page's one search bar, which covers
 * the catalogue and both providers' own libraries.
 */
export function ProviderShelves({ persona }: { persona: string }) {
  const [items, setItems] = useState<Record<Provider, Item[] | null>>({ Pluralsight: null, 'Microsoft Learn': null })
  const [status, setStatus] = useState<Integration[]>([])
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    for (const provider of ['Pluralsight', 'Microsoft Learn'] as Provider[]) {
      fetchItems({ source: provider, persona }, ctrl.signal)
        .then((found) => setItems((prev) => ({ ...prev, [provider]: found })))
        .catch((e: unknown) => {
          if (!isAbort(e)) setItems((prev) => ({ ...prev, [provider]: [] }))
        })
    }
    fetchIntegrations(ctrl.signal)
      .then(setStatus)
      .catch(() => setStatus([]))
    return () => ctrl.abort()
  }, [persona, open])

  return (
    <>
      <Shelf provider="Pluralsight" items={items.Pluralsight} status={status.find((s) => s.id === 'pluralsight')} persona={persona} onOpen={setOpen} />
      <Shelf
        provider="Microsoft Learn"
        items={items['Microsoft Learn']}
        status={status.find((s) => s.id === 'microsoft_learn')}
        persona={persona}
        onOpen={setOpen}
      />
      <CourseDrawer itemId={open} onClose={() => setOpen(null)} />
    </>
  )
}
