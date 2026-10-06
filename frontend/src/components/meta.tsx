import { FileSpreadsheet, FileText, MessagesSquare, Presentation } from 'lucide-react'
import type { SourceType } from '../types'
import { label } from '../lib/format'
import { Badge, cn } from './ui'

/** Only critical stands out; the rest stay neutral so priority doesn't compete with content. */
export function PriorityBadge({ priority }: { priority: string | null | undefined }) {
  if (!priority || priority === 'none') return null
  return (
    <Badge tone={priority === 'critical' ? 'red' : 'slate'}>
      {label(priority)} priority
    </Badge>
  )
}

export function TopicBadge({ topic }: { topic: string | null | undefined }) {
  if (!topic) return null
  return <Badge tone="slate">{label(topic)}</Badge>
}

export function SourceIcon({ type, className = 'size-4' }: { type: SourceType | string; className?: string }) {
  const cls = cn(className, 'text-slate-500 dark:text-slate-400')
  switch (type) {
    case 'meeting':
      return <MessagesSquare className={cls} />
    case 'pptx':
      return <Presentation className={cls} />
    case 'xlsx':
      return <FileSpreadsheet className={cls} />
    default:
      return <FileText className={cls} />
  }
}

export const SOURCE_LABEL: Record<string, string> = {
  meeting: 'Meeting',
  docx: 'Word',
  pptx: 'Slides',
  xlsx: 'Spreadsheet',
}

export function MetaBadges({ topic, priority, products, type }: {
  topic?: string | null
  priority?: string | null
  products?: string[]
  type?: string
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {type && <Badge tone="outline">{SOURCE_LABEL[type] ?? type}</Badge>}
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

/** Confidence in words first; the number is secondary. */
export function ConfidenceMeter({ value, threshold = 0.55 }: { value: number | null; threshold?: number }) {
  if (value === null) return null
  const ok = value >= threshold
  const word = ok ? (value >= 0.8 ? 'High confidence' : 'Confident') : 'Low confidence'
  return (
    <div
      className="flex items-center gap-2"
      title={`Confidence ${(value * 100).toFixed(0)}% (threshold ${(threshold * 100).toFixed(0)}%): retrieval relevance, reranking and citation coverage`}
    >
      <div className="relative h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div
          className={cn('h-full rounded-full', ok ? 'bg-brand-500' : 'bg-amber-500')}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
        <div className="absolute top-0 h-full w-px bg-slate-500/60" style={{ left: `${threshold * 100}%` }} />
      </div>
      <span className={cn('text-xs font-medium', ok ? 'text-brand-700 dark:text-brand-200' : 'text-amber-700 dark:text-amber-300')}>
        {word}
      </span>
      <span className="text-xs text-slate-400 tabular-nums">{(value * 100).toFixed(0)}%</span>
    </div>
  )
}
