import { useEffect, useState } from 'react'
import { isAbort } from '../lib/api'
import { useHub } from '../lib/hub'
import { fetchJourneys, type JourneysHome } from '../lib/journeys'
import { usePersona } from '../lib/personaContext'
import '../home.css'
import { SuperAgentChat } from './home/SuperAgentChat'

// When the person's jobs suggest nothing of their own.
const EXAMPLES = [
  'Screen a client against sanctions lists',
  'Who ultimately owns a company',
  'Summarise a contract',
  'Check W-8 and FATCA classification',
]

/**
 * The Super Agent, on a page of its own below Home: one conversation that
 * takes any request and answers it from every pillar. Home's ask bar lands
 * here with the question already asked.
 */
export function SuperAgentPage() {
  const data = useHub()
  const { persona } = usePersona()
  const [work, setWork] = useState<JourneysHome | null>(null)

  // The person's jobs give the suggestions, in their own words.
  useEffect(() => {
    const ctrl = new AbortController()
    fetchJourneys(persona, ctrl.signal)
      .then(setWork)
      .catch((e: unknown) => {
        if (!isAbort(e)) setWork(null)
      })
    return () => ctrl.abort()
  }, [persona])

  return (
    <SuperAgentChat
      // A persona preview starts afresh: same conversations, a clean composer.
      key={`${data.user.id}.${persona}`}
      userId={data.user.id}
      firstName={data.user.first_name}
      initials={data.user.initials}
      persona={persona}
      personaLabel={work?.persona_label ?? data.user.persona.label}
      examples={work?.examples.length ? work.examples : EXAMPLES}
    />
  )
}
