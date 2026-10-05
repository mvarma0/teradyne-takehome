import { FileSpreadsheet, FileText, MessagesSquare, Presentation } from 'lucide-react'
import type { SourceType } from '../types'
import { humanize } from '../lib/format'
import { Badge, type Tone } from './ui'

const PRIORITY_TONE: Record<string, Tone> = {
  critical: 'red',
  high: 'amber',
  medium: 'blue',
  low: 'slate',
  none: 'slate',
}

export function PriorityBadge({ priority }: { priority: string | null | undefined }) {
  if (!priority || priority === 'none') return null
  return <Badge tone={PRIORITY_TONE[priority] ?? 'slate'}>{humanize(priority)}</Badge>
}

export function TopicBadge({ topic }: { topic: string | null | undefined }) {
  if (!topic) return null
  return <Badge tone="violet">{humanize(topic)}</Badge>
}

export function SourceIcon({ type, className = 'size-4' }: { type: SourceType | string; className?: string }) {
  switch (type) {
    case 'meeting':
      return <MessagesSquare className={`${className} text-sky-500`} />
    case 'pptx':
      return <Presentation className={`${className} text-orange-500`} />
    case 'xlsx':
      return <FileSpreadsheet className={`${className} text-emerald-500`} />
    default:
      return <FileText className={`${className} text-blue-500`} />
  }
}

export const SOURCE_LABEL: Record<string, string> = {
  meeting: 'Meeting',
  docx: 'Word',
  pptx: 'Slides',
  xlsx: 'Excel',
}

export function MetaBadges({ topic, priority, products, type }: {
  topic?: string | null
  priority?: string | null
  products?: string[]
  type?: string
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {type && <Badge>{SOURCE_LABEL[type] ?? type}</Badge>}
      <TopicBadge topic={topic} />
      <PriorityBadge priority={priority} />
      {products?.map((p) => (
        <Badge key={p} tone="brand">
          {p}
        </Badge>
      ))}
    </div>
  )
}

export function ConfidenceMeter({ value, threshold = 0.55 }: { value: number | null; threshold?: number }) {
  if (value === null) return null
  const tone = value >= threshold ? 'bg-emerald-500' : value >= threshold * 0.7 ? 'bg-amber-500' : 'bg-rose-500'
  return (
    <div className="flex items-center gap-1.5" title={`Confidence ${(value * 100).toFixed(0)}% (threshold ${(threshold * 100).toFixed(0)}%)`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-[11px] font-medium text-slate-500 tabular-nums dark:text-slate-400">
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  )
}
