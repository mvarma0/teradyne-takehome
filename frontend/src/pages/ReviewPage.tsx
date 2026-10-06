import { CheckCircle2, ChevronDown, ClipboardCheck, ExternalLink, MessageSquareWarning, Send } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { DocumentDrawer, SourceCard } from '../components/citations'
import { ConfidenceMeter } from '../components/meta'
import { Badge, Button, Card, cn, EmptyState, ErrorBanner, inputClass, PageHeader, Spinner, type Tone } from '../components/ui'
import { label, relativeTime } from '../lib/format'
import type { Citation, Gap } from '../types'

const TYPE_META: Record<Gap['type'], { label: string; tone: Tone }> = {
  low_confidence: { label: 'Low confidence', tone: 'amber' },
  rejected: { label: 'Rejected', tone: 'red' },
  correction: { label: 'Correction', tone: 'blue' },
}
const STATUS_TONE: Record<Gap['review_status'], Tone> = { pending: 'amber', reviewed: 'slate', resolved: 'green' }

export default function ReviewPage() {
  const [items, setItems] = useState<Gap[] | null>(null)
  const [counts, setCounts] = useState<{ pending: number; total: number; by_type: Record<string, number> } | null>(null)
  const [status, setStatus] = useState('pending')
  const [type, setType] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<Citation | null>(null)

  const load = useCallback(() => {
    api
      .reviewQueue({ status: status || undefined, type: type || undefined })
      .then((q) => {
        setItems(q.items)
        setCounts(q.counts)
      })
      .catch((e) => setError(e.message))
  }, [status, type])
  useEffect(load, [load])

  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle="Knowledge gaps and corrections captured from users: low-confidence answers, rejections and corrections."
      />
      <div className="mb-5 grid gap-3 sm:grid-cols-4">
        <CountTile label="Pending review" value={counts?.pending} highlight />
        <CountTile label="Low confidence" value={counts?.by_type.low_confidence ?? 0} />
        <CountTile label="Rejected answers" value={counts?.by_type.rejected ?? 0} />
        <CountTile label="Corrections" value={counts?.by_type.correction ?? 0} />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-slate-300/80 bg-white p-0.5 text-sm dark:border-slate-700 dark:bg-[#121a1d]">
          {['pending', 'reviewed', 'resolved', ''].map((s) => (
            <button
              key={s || 'all'}
              onClick={() => setStatus(s)}
              className={cn(
                'rounded-md px-3 py-1 capitalize',
                status === s ? 'bg-brand-600 text-white dark:bg-brand-500' : 'text-slate-600 dark:text-slate-400',
              )}
            >
              {s || 'all'}
            </button>
          ))}
        </div>
        <select value={type} onChange={(e) => setType(e.target.value)} className={`${inputClass} w-auto!`}>
          <option value="">All types</option>
          {Object.entries(TYPE_META).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </select>
      </div>
      <ErrorBanner error={error} />
      {!items && !error && <Spinner />}
      {items?.length === 0 && (
        <EmptyState icon={<ClipboardCheck className="size-10" />} title="Queue is clear">
          Nothing {status || 'here'} right now. Low-confidence answers, rejections and corrections land here.
        </EmptyState>
      )}
      <div className="space-y-3">
        {items?.map((g) => <GapCard key={g.id} gap={g} onChange={load} onOpen={setDrawer} />)}
      </div>
      <DocumentDrawer docId={drawer?.doc_id ?? null} chunkId={drawer?.chunk_id} onClose={() => setDrawer(null)} />
    </>
  )
}

function CountTile({ label, value, highlight }: { label: string; value: number | undefined; highlight?: boolean }) {
  return (
    <Card className={cn('p-4', highlight && value ? 'border-amber-300 dark:border-amber-700' : '')}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? '—'}</p>
    </Card>
  )
}

function GapCard({ gap: g, onChange, onOpen }: { gap: Gap; onChange: () => void; onOpen: (c: Citation) => void }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState(g.reviewer_note ?? '')
  const [busy, setBusy] = useState<string | null>(null)
  const act = async (s: Gap['review_status']) => {
    setBusy(s)
    try {
      await api.review(g.id, s, note || undefined)
      onChange()
    } finally {
      setBusy(null)
    }
  }
  const meta = TYPE_META[g.type]
  const sent = g.routing.filter((r) => r.status === 'sent')
  return (
    <Card className="overflow-hidden">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-start gap-3 p-4 text-left">
        <MessageSquareWarning className="mt-0.5 size-4 shrink-0 text-slate-400" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={meta.tone}>{meta.label}</Badge>
            <Badge tone={STATUS_TONE[g.review_status]}>{label(g.review_status)}</Badge>
            {sent.length > 0 && (
              <Badge tone="green">
                <Send className="size-3" /> Asked {sent.map((r) => r.person).join(', ')}
              </Badge>
            )}
            <span className="text-xs text-slate-400">
              {relativeTime(g.created_at)}
              {g.submitted_by && ` · by ${g.submitted_by}`}
            </span>
          </div>
          <p className="mt-1.5 text-sm font-medium">{g.query_text}</p>
          {g.type === 'correction' && g.correction_text && (
            <p className="mt-1 text-sm text-sky-700 dark:text-sky-300">
              <span className="font-medium">Correction:</span> {g.correction_text}
            </p>
          )}
          {g.type === 'rejected' && g.reason && (
            <p className="mt-1 text-sm text-rose-700 dark:text-rose-300">
              <span className="font-medium">Reason:</span> {g.reason}
            </p>
          )}
        </div>
        <ConfidenceMeter value={g.confidence} />
        <ChevronDown className={cn('mt-0.5 size-4 shrink-0 text-slate-400 transition', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-slate-100 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-950/30">
          {g.original_answer && (
            <div>
              <h4 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">Original answer</h4>
              <p className="rounded-lg bg-white p-3 text-sm whitespace-pre-wrap dark:bg-[#121a1d]">{g.original_answer}</p>
            </div>
          )}
          {g.routing.length > 0 && (
            <div>
              <h4 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">Routing</h4>
              <div className="space-y-2">
                {g.routing.map((r) => (
                  <div key={r.routing_id ?? r.id} className="rounded-md bg-white p-3 text-sm dark:bg-[#121a1d]">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{r.person}</span>
                      {r.role && <span className="text-xs text-slate-500">{r.role}</span>}
                      <Badge tone={r.status === 'sent' ? 'green' : 'slate'}>{label(r.status)}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{r.reason}</p>
                    <p className="mt-1.5 text-[13px] italic">“{r.edited_question ?? r.draft_question}”</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {g.citations.length > 0 && (
            <div>
              <h4 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">Retrieved sources</h4>
              <div className="grid gap-2 md:grid-cols-2">
                {g.citations.slice(0, 4).map((c) => (
                  <div key={c.chunk_id} className="rounded-md bg-white p-3 dark:bg-[#121a1d]">
                    <SourceCard citation={c} onOpen={onOpen} compact />
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reviewer note (e.g. doc updated, answer added to FAQ)" className={`${inputClass} min-w-[260px] flex-1`} />
            <Button onClick={() => act('reviewed')} loading={busy === 'reviewed'}>
              Mark reviewed
            </Button>
            <Button variant="primary" onClick={() => act('resolved')} loading={busy === 'resolved'}>
              <CheckCircle2 className="size-3.5" /> Resolve
            </Button>
            {g.review_status !== 'pending' && (
              <Button variant="ghost" onClick={() => act('pending')} loading={busy === 'pending'}>
                Reopen
              </Button>
            )}
            {g.conversation_id && (
              <Link to={`/chat/${g.conversation_id}`} className="inline-flex h-9 items-center gap-1 px-2 text-sm text-brand-600 hover:underline dark:text-brand-100">
                Open conversation <ExternalLink className="size-3.5" />
              </Link>
            )}
          </div>
          {g.reviewed_at && <p className="text-xs text-slate-400">Last reviewed {relativeTime(g.reviewed_at)}</p>}
        </div>
      )}
    </Card>
  )
}
