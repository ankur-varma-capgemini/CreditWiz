import type { Pillar, Section } from './types'

// Words that carry no subject. "How do I get an agent approved" is about
// approval; the rest would match every section on Nexus, "agent" included,
// since nearly everything here mentions one. Mirrors the backend's list in
// app/text.py, which matches learning items and journeys the same way.
const STOP = new Set(
  (
    'a about against agent agents all also an and any are at be by can could do does for from get give has have how i ' +
    'in into is it just like me my need new of on or our out please should show some than that the their them then ' +
    'there they this to use using want was were what when where which who why will with would you your'
  ).split(' '),
)
const SUFFIXES = ['ations', 'ation', 'ings', 'ing', 'ions', 'ion', 'ers', 'er', 'ed', 'es', 'ly', 'al', 's', 'e']

/** One suffix off, never below four letters: "approved" and "approval" both
 *  become "approv", "screening" becomes "screen". */
function stem(word: string): string {
  const suffix = SUFFIXES.find((s) => word.endsWith(s) && word.length - s.length >= 4)
  return suffix ? word.slice(0, -suffix.length) : word
}

/** The words of a query worth matching, as stems. */
export function queryStems(q: string): string[] {
  const words = q.toLowerCase().match(/[a-z0-9]+/g) ?? []
  return [...new Set(words.filter((w) => w.length > 2 && !STOP.has(w)).map(stem))]
}

export interface SectionHit {
  pillar: Pillar
  section: Section
}

/**
 * Pillar sections that answer a query, best first. A section needs at least
 * half the query's subject words, so a sentence still finds its section
 * without one common word pulling in the whole hub.
 */
export function matchSections(pillars: Pillar[], q: string, limit = 5): SectionHit[] {
  const stems = queryStems(q)
  if (!stems.length) return []
  // A stem counts only where a word starts: "check" and "list" are not a
  // match for "checklist". Stems are letters and digits, so safe in a pattern.
  const starts = stems.map((s) => new RegExp(`\\b${s}`))
  const needed = Math.ceil(stems.length / 2)
  return pillars
    .flatMap((pillar) =>
      pillar.sections.map((section) => {
        const text = `${pillar.short_title} ${section.title} ${section.blurb}`.toLowerCase()
        return { pillar, section, score: starts.filter((p) => p.test(text)).length }
      }),
    )
    .filter((h) => h.score >= needed)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(({ pillar, section }) => ({ pillar, section }))
}
