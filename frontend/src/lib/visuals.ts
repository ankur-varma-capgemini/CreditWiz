import {
  Bot,
  BookOpen,
  CreditCard,
  FileText,
  Headset,
  IdCard,
  Landmark,
  Layers,
  LineChart,
  Network,
  Newspaper,
  Receipt,
  Scale,
  ScanSearch,
  ScrollText,
  Send,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

// Things with no picture of their own share one neutral cover in every pillar
// (Cover.tsx); nothing is colour-coded. The icon is what tells them apart.

// What a business domain or category is about, as an icon. The specific
// compliance jobs come first, so each keeps its own icon rather than all
// sharing the compliance shield.
const SUBJECT: [RegExp, LucideIcon][] = [
  [/identit|verif/i, IdCard],
  [/sanction|screen/i, ScanSearch],
  [/media|news/i, Newspaper],
  [/ownership|hierarch/i, Network],
  [/\btax\b|fatca/i, Receipt],
  [/outreach/i, Send],
  [/^polic/i, ScrollText],
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
