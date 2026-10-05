import {
  Bot,
  BookOpen,
  CreditCard,
  FileText,
  Headset,
  Landmark,
  Layers,
  LineChart,
  Scale,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

/**
 * How things look when they have no picture of their own: a colour (tone)
 * and an icon, always the same for the same thing, so a card is recognisable
 * at a glance and a grid reads as designed rather than empty.
 */
export type Tone = 'navy' | 'sky' | 'rose' | 'indigo' | 'violet' | 'crimson' | 'teal' | 'emerald' | 'amber' | 'slate'

// Red, Pluralsight's pink and Microsoft's blue are kept for what they mean,
// so a seed never lands on them by chance.
const TONES: Tone[] = ['navy', 'teal', 'indigo', 'violet', 'emerald', 'amber', 'slate']

/** The same seed always gets the same tone. */
export function toneFor(seed: string): Tone {
  let h = 0
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return TONES[h % TONES.length]
}

// Outside providers keep their own colours, so a course says where it comes from.
const PROVIDER: [RegExp, Tone][] = [
  [/pluralsight/i, 'rose'],
  [/microsoft/i, 'sky'],
  [/linkedin/i, 'indigo'],
  [/udemy/i, 'violet'],
  [/google/i, 'teal'],
  [/aws|amazon/i, 'amber'],
  [/ibm/i, 'navy'],
  [/github/i, 'slate'],
]

// The hub's own content, by kind: a row of mixed kinds reads as such, and a
// row of MUFG's own does not turn red.
const KIND: Record<string, Tone> = {
  course: 'navy',
  video: 'violet',
  guide: 'teal',
  'best-practice': 'emerald',
  'quick-reference': 'indigo',
  documentation: 'slate',
  confluence: 'slate',
}

export function providerTone(provider: string, kind = ''): Tone {
  return PROVIDER.find(([pattern]) => pattern.test(provider))?.[1] ?? KIND[kind] ?? toneFor(provider || kind || 'hub')
}

// What a business domain or category is about, as an icon.
const SUBJECT: [RegExp, LucideIcon][] = [
  [/fraud|risk/i, ShieldAlert],
  [/complian|kyc|aml|sanction|regulat|policy/i, ShieldCheck],
  [/lend|credit|loan|bank/i, Landmark],
  [/onboard/i, UserPlus],
  [/card/i, CreditCard],
  [/collect|recover|payment/i, Wallet],
  [/service|support|contact/i, Headset],
  [/legal|contract/i, Scale],
  [/operat|process|workflow/i, Settings2],
  [/market|trading|treasur|invest/i, LineChart],
  [/learn|train|course/i, BookOpen],
  [/document|report|memo|summar/i, FileText],
  [/data|analyt/i, Layers],
  [/prompt|write|draft/i, Sparkles],
]

export function subjectIcon(subject: string, fallback: LucideIcon = Bot): LucideIcon {
  return SUBJECT.find(([pattern]) => pattern.test(subject))?.[1] ?? fallback
}
