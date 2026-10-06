export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`

export const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? '—' : v.toFixed(digits)

export const ms = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`
  return new Date(iso).toLocaleDateString()
}

export const fileName = (path: string) => path.split('/').pop() ?? path

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')

export const humanize = (s: string | null | undefined) =>
  s ? s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—'

const LABELS: Record<string, string> = {
  npi_program: 'NPI program',
  test_engineering: 'Test engineering',
  quality_compliance: 'Quality & compliance',
  executive_strategy: 'Executive strategy',
  supply_chain: 'Supply chain',
  yield: 'Yield',
  design: 'Design',
  customer: 'Customer',
  other: 'Other',
  low_confidence: 'Low confidence',
}

/** Sentence-case label for enum values (topics, priorities, gap types). */
export const label = (s: string | null | undefined) =>
  !s ? '—' : (LABELS[s] ?? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' '))

/** Titles written in all caps (e.g. a document banner) read better in title case. */
export const displayTitle = (title: string | null | undefined, fallback = '') => {
  const t = (title ?? fallback).trim()
  if (t.length < 6 || t !== t.toUpperCase()) return t
  return t.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(Npi|Pe|Fa|Ate|Htol|Aec|Q100|Sop|8d)\b/g, (w) => w.toUpperCase()).replace(/\bFastchip\b/g, 'FastChip')
}

/** Label for the people attached to a source: attendees for meetings, author otherwise. */
export const peopleLabel = (type: string, count: number) =>
  type === 'meeting' ? 'Attendees' : count > 1 ? 'Authors' : 'Author'

const NAME_KEY = 'fastchip.userName'
export const getUserName = () => {
  try {
    return localStorage.getItem(NAME_KEY) ?? ''
  } catch {
    return ''
  }
}
export const setUserName = (name: string) => {
  try {
    localStorage.setItem(NAME_KEY, name)
  } catch {
    /* storage unavailable */
  }
}
