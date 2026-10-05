import {
  AlertTriangle,
  ArrowUp,
  Check,
  ChevronDown,
  Copy,
  Filter,
  Pencil,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { fileName, getUserName, humanize, initials, ms } from '../lib/format'
import type { AnswerPayload, Citation, DocumentMeta, QueryFilters, Routing } from '../types'
import { AnswerMarkdown, SourceCard } from './citations'
import { ConfidenceMeter, PriorityBadge, SourceIcon, TopicBadge } from './meta'
import { Badge, Button, cn, inputClass, Modal } from './ui'

export interface UiMessage {
  key: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  stage?: string
  standalone?: string
  citations?: Citation[]
  documents?: DocumentMeta[]
  guard?: { category: string; reason: string }
  payload?: AnswerPayload
  error?: string
}

const STAGES: Record<string, string> = {
  guardrails: 'Checking the question',
  retrieving: 'Searching meetings & documents',
  generating: 'Writing a grounded answer',
  routing: 'Finding who could answer',
}

export function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm whitespace-pre-wrap text-white shadow-sm">
        {text}
      </div>
    </div>
  )
}

export function AssistantMessage({ msg, threshold, onOpenCitation, onPatch }: {
  msg: UiMessage
  threshold: number
  onOpenCitation: (c: Citation) => void
  onPatch: (patch: Partial<AnswerPayload>) => void
}) {
  const p = msg.payload
  const citations = p?.citations ?? msg.citations ?? []
  const text = p ? p.answer : msg.content
  const guardCategory = p?.guardrails?.category ?? msg.guard?.category
  const [showSources, setShowSources] = useState(false)
  const cited = new Set(p?.cited ?? [])
  const blocked = guardCategory === 'prompt_injection' || guardCategory === 'off_topic'

  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-sm">
        <Sparkles className="size-3.5" />
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {msg.streaming && msg.stage && !text && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="relative flex size-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-500 opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-brand-500" />
            </span>
            {STAGES[msg.stage] ?? 'Working'}
            {msg.stage === 'retrieving' && msg.standalone && msg.standalone !== msg.content && (
              <span className="truncate text-xs text-slate-400">“{msg.standalone}”</span>
            )}
          </div>
        )}

        {blocked && (
          <div className="flex items-center gap-2 text-xs font-medium text-amber-700 dark:text-amber-400">
            <ShieldAlert className="size-3.5" />
            {guardCategory === 'prompt_injection' ? 'Blocked by prompt-injection guardrail' : 'Outside the knowledge base scope'}
          </div>
        )}

        {msg.error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
            {msg.error}
          </div>
        ) : (
          (text || msg.streaming) && (
            <AnswerMarkdown text={text} citations={citations} onOpen={onOpenCitation} streaming={msg.streaming && !!text} />
          )
        )}

        {p && p.status !== 'refused' && p.status !== 'blocked' && guardCategory === 'knowledge_question' && (
          <>
            <AnswerMeta payload={p} threshold={threshold} />
            {p.dropped_claims.length > 0 && (
              <p className="flex items-center gap-1.5 text-xs text-slate-500">
                <ShieldCheck className="size-3.5 text-emerald-500" />
                {p.dropped_claims.length} unsupported statement{p.dropped_claims.length > 1 && 's'} removed
                (no citation)
              </p>
            )}
            {citations.length > 0 && (
              <div>
                <button
                  onClick={() => setShowSources((s) => !s)}
                  className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                >
                  <ChevronDown className={cn('size-3.5 transition', showSources && 'rotate-180')} />
                  {citations.length} sources · {p.documents.length} documents
                </button>
                {!showSources && <SourceStrip citations={citations} cited={cited} onOpen={onOpenCitation} />}
                {showSources && (
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {citations.map((c) => (
                      <div
                        key={c.chunk_id}
                        className={cn(
                          'rounded-xl border p-3',
                          cited.has(c.n)
                            ? 'border-brand-100 bg-brand-50/40 dark:border-brand-700/40 dark:bg-brand-700/10'
                            : 'border-slate-200 dark:border-slate-800',
                        )}
                      >
                        <SourceCard citation={c} onOpen={onOpenCitation} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {(p.routing?.length ?? 0) > 0 && <RoutingPanel routing={p.routing} confident={p.confident} />}
            <FeedbackBar payload={p} onPatch={onPatch} />
          </>
        )}
      </div>
    </div>
  )
}

function SourceStrip({ citations, cited, onOpen }: {
  citations: Citation[]
  cited: Set<number>
  onOpen: (c: Citation) => void
}) {
  const seen = new Set<string>()
  const unique = citations.filter((c) => (cited.size === 0 || cited.has(c.n)) && !seen.has(c.doc_id) && seen.add(c.doc_id))
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {unique.map((c) => (
        <button
          key={c.doc_id}
          onClick={() => onOpen(c)}
          className="flex max-w-[260px] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs shadow-sm hover:border-brand-500 dark:border-slate-700 dark:bg-slate-900"
          title={`${c.source_file} — ${c.people_label}: ${c.people.join(', ')}`}
        >
          <SourceIcon type={c.source_type} className="size-3.5 shrink-0" />
          <span className="truncate">{fileName(c.source_file)}</span>
          <span className="truncate text-slate-400">· {c.people[0] ?? 'unknown'}</span>
        </button>
      ))}
    </div>
  )
}

const PRIORITY_RANK = ['none', 'low', 'medium', 'high', 'critical']

function AnswerMeta({ payload: p, threshold }: { payload: AnswerPayload; threshold: number }) {
  const citedDocs = new Set(p.citations.filter((c) => p.cited?.includes(c.n)).map((c) => c.doc_id))
  const docs = p.documents.filter((d) => citedDocs.size === 0 || citedDocs.has(d.doc_id))
  const topics = [...new Set(docs.map((d) => d.topic_domain).filter(Boolean))] as string[]
  const priority = docs.map((d) => d.priority ?? 'none').sort((a, b) => PRIORITY_RANK.indexOf(b) - PRIORITY_RANK.indexOf(a))[0]
  const products = [...new Set(docs.flatMap((d) => d.products))]
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500">
      <ConfidenceMeter value={p.confidence} threshold={threshold} />
      {p.confident === false && (
        <Badge tone="amber">
          <AlertTriangle className="size-3" /> Low confidence
        </Badge>
      )}
      {p.status === 'rejected' && <Badge tone="red">Rejected</Badge>}
      {p.status === 'corrected' && <Badge tone="blue">Corrected</Badge>}
      {(p.guardrails?.pii_redactions ?? 0) > 0 && <Badge tone="violet">PII redacted</Badge>}
      {topics.map((t) => (
        <TopicBadge key={t} topic={t} />
      ))}
      <PriorityBadge priority={priority} />
      {products.slice(0, 3).map((x) => (
        <Badge key={x} tone="brand">
          {x}
        </Badge>
      ))}
      <span className="tabular-nums">{ms(p.latency_ms)}</span>
    </div>
  )
}

export function RoutingPanel({ routing, confident }: { routing: Routing[]; confident: boolean | null }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900/60 dark:bg-amber-950/20">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-900 dark:text-amber-200">
        <UserRound className="size-4" />
        {confident === false ? "I'm not confident in this answer. These people may know:" : 'Suggested people to ask'}
      </div>
      <div className="space-y-2">
        {routing.map((r) => (
          <RoutingCard key={r.routing_id ?? r.id ?? r.person} routing={r} />
        ))}
      </div>
    </div>
  )
}

function RoutingCard({ routing }: { routing: Routing }) {
  const id = routing.routing_id ?? routing.id
  const [question, setQuestion] = useState(routing.edited_question ?? routing.draft_question)
  const [status, setStatus] = useState(routing.status ?? 'suggested')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const send = async () => {
    if (!id) return
    setBusy(true)
    try {
      const r = await api.sendRouting(id, question, getUserName() || undefined)
      setStatus(r.status ?? 'sent')
      setEditing(false)
    } finally {
      setBusy(false)
    }
  }
  const dismiss = async () => {
    if (!id) return
    await api.dismissRouting(id)
    setStatus('dismissed')
  }
  if (status === 'dismissed') return null
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-start gap-2.5">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {initials(routing.person)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium">{routing.person}</span>
            {routing.role && <span className="text-xs text-slate-500">{routing.role}</span>}
            {status === 'sent' && (
              <Badge tone="green">
                <Check className="size-3" /> Sent
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
            <span className="font-medium">Why:</span> {routing.reason}
          </p>
          {routing.matched_sources?.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {routing.matched_sources.map((s) => (
                <Badge key={s.source_file} title={s.snippet}>
                  {fileName(s.source_file)}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="mt-2.5">
        <label className="mb-1 block text-[11px] font-medium tracking-wide text-slate-500 uppercase">
          Draft question
        </label>
        {editing || status !== 'sent' ? (
          <textarea
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value)
              setEditing(true)
            }}
            rows={3}
            disabled={status === 'sent'}
            className={cn(inputClass, 'resize-y text-[13px] leading-relaxed')}
          />
        ) : (
          <p className="rounded-lg bg-slate-50 p-2 text-[13px] dark:bg-slate-800/60">{question}</p>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-end gap-1.5">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            navigator.clipboard?.writeText(question)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          }}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} Copy
        </Button>
        {status !== 'sent' && (
          <>
            <Button size="sm" variant="ghost" onClick={dismiss}>
              <X className="size-3.5" /> Dismiss
            </Button>
            <Button size="sm" variant="primary" onClick={send} loading={busy} disabled={!question.trim()}>
              <Send className="size-3.5" /> Send to {routing.person.split(' ')[0]}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

function FeedbackBar({ payload: p, onPatch }: { payload: AnswerPayload; onPatch: (patch: Partial<AnswerPayload>) => void }) {
  const [rating, setRating] = useState<'up' | 'down' | null>(p.feedback ?? null)
  const [dialog, setDialog] = useState<'correct' | 'reject' | null>(null)
  const [text, setText] = useState('')
  const [name, setName] = useState(getUserName())
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  const rate = async (r: 'up' | 'down') => {
    const next = rating === r ? null : r
    setRating(next)
    await api.feedback(p.query_id, next)
  }
  const submit = async () => {
    setBusy(true)
    try {
      if (dialog === 'correct') {
        await api.correct(p.query_id, text, name || undefined)
        onPatch({ status: 'corrected' })
        setDone('Correction captured for review')
      } else {
        const gap = await api.reject(p.query_id, text, name || undefined)
        onPatch({ status: 'rejected', routing: gap.routing })
        setDone('Rejection captured, see suggested people below')
      }
      setDialog(null)
      setText('')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      <IconToggle active={rating === 'up'} onClick={() => rate('up')} title="Helpful">
        <ThumbsUp className="size-3.5" />
      </IconToggle>
      <IconToggle active={rating === 'down'} onClick={() => rate('down')} title="Not helpful">
        <ThumbsDown className="size-3.5" />
      </IconToggle>
      <span className="mx-1 h-4 w-px bg-slate-200 dark:bg-slate-700" />
      <Button size="sm" variant="ghost" onClick={() => setDialog('correct')}>
        <Pencil className="size-3.5" /> Correct
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setDialog('reject')}>
        <X className="size-3.5" /> Reject
      </Button>
      {done && <span className="ml-1 text-xs text-emerald-600 dark:text-emerald-400">{done}</span>}
      <Modal
        open={dialog !== null}
        onClose={() => setDialog(null)}
        title={dialog === 'correct' ? 'Correct this answer' : 'Reject this answer'}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              variant={dialog === 'reject' ? 'danger' : 'primary'}
              onClick={submit}
              loading={busy}
              disabled={dialog === 'correct' && !text.trim()}
            >
              {dialog === 'correct' ? 'Submit correction' : 'Reject & find who knows'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="rounded-lg bg-slate-50 p-2.5 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
            <span className="font-medium">Question:</span> {p.query}
          </div>
          <textarea
            autoFocus
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={dialog === 'correct' ? 'What is the correct answer?' : 'What is wrong with the answer? (optional)'}
            className={inputClass}
          />
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name (optional)" className={inputClass} />
          <p className="text-xs text-slate-500">Captured with the original question and answer in the team-lead review queue.</p>
        </div>
      </Modal>
    </div>
  )
}

function IconToggle({ active, onClick, title, children }: {
  active: boolean
  onClick: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        'rounded-md p-1.5 transition',
        active
          ? 'bg-brand-50 text-brand-600 dark:bg-brand-700/30 dark:text-brand-100'
          : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800',
      )}
    >
      {children}
    </button>
  )
}

const TOPICS = ['yield', 'design', 'test_engineering', 'npi_program', 'supply_chain', 'customer', 'quality_compliance', 'executive_strategy']

export function Composer({ onSend, disabled, onStop }: {
  onSend: (text: string, filters: QueryFilters | null) => void
  disabled: boolean
  onStop?: () => void
}) {
  const [text, setText] = useState('')
  const [filters, setFilters] = useState<QueryFilters>({})
  const [showFilters, setShowFilters] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])
  const active = Object.values(filters).filter(Boolean).length
  const submit = () => {
    if (!text.trim() || disabled) return
    onSend(text.trim(), active ? filters : null)
    setText('')
  }
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-lg shadow-slate-200/50 focus-within:border-brand-500 dark:border-slate-700 dark:bg-slate-900 dark:shadow-none">
      {showFilters && (
        <div className="grid gap-2 border-b border-slate-100 p-3 sm:grid-cols-3 dark:border-slate-800">
          <select
            value={filters.topic_domain ?? ''}
            onChange={(e) => setFilters({ ...filters, topic_domain: e.target.value || undefined })}
            className={inputClass}
          >
            <option value="">Any topic</option>
            {TOPICS.map((t) => (
              <option key={t} value={t}>
                {humanize(t)}
              </option>
            ))}
          </select>
          <select
            value={filters.source_type ?? ''}
            onChange={(e) => setFilters({ ...filters, source_type: e.target.value || undefined })}
            className={inputClass}
          >
            <option value="">Any source</option>
            <option value="meeting">Meetings</option>
            <option value="docx">Word</option>
            <option value="pptx">Slides</option>
            <option value="xlsx">Excel</option>
          </select>
          <select
            value={filters.priority ?? ''}
            onChange={(e) => setFilters({ ...filters, priority: e.target.value || undefined })}
            className={inputClass}
          >
            <option value="">Any priority</option>
            {['critical', 'high', 'medium', 'low'].map((p) => (
              <option key={p} value={p}>
                {humanize(p)}
              </option>
            ))}
          </select>
          <input
            value={filters.person ?? ''}
            onChange={(e) => setFilters({ ...filters, person: e.target.value || undefined })}
            placeholder="Person (attendee / author)"
            className={inputClass}
          />
          <input
            type="date"
            value={filters.date_from ?? ''}
            onChange={(e) => setFilters({ ...filters, date_from: e.target.value || undefined })}
            className={inputClass}
            title="From date"
          />
          <input
            type="date"
            value={filters.date_to ?? ''}
            onChange={(e) => setFilters({ ...filters, date_to: e.target.value || undefined })}
            className={inputClass}
            title="To date"
          />
        </div>
      )}
      <div className="flex items-end gap-2 p-2">
        <button
          onClick={() => setShowFilters((s) => !s)}
          className={cn(
            'relative rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800',
            active > 0 && 'text-brand-600',
          )}
          title="Filters"
        >
          <Filter className="size-4" />
          {active > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-brand-600 text-[9px] text-white">
              {active}
            </span>
          )}
        </button>
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          placeholder="Ask about meetings, decisions, yield, test, quality…"
          className="max-h-[200px] flex-1 resize-none bg-transparent py-2 text-sm outline-none placeholder:text-slate-400"
        />
        {disabled && onStop ? (
          <button onClick={onStop} className="rounded-lg bg-slate-200 p-2 text-slate-700 dark:bg-slate-700 dark:text-slate-200" title="Stop">
            <span className="block size-4 rounded-sm bg-current p-1" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim()}
            className="rounded-lg bg-brand-600 p-2 text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-40"
            title="Send"
          >
            <ArrowUp className="size-4" />
          </button>
        )}
      </div>
    </div>
  )
}

export const SUGGESTIONS = [
  { icon: <Search className="size-4" />, text: 'What caused the low first-silicon yield on Volta-7?' },
  { icon: <UserRound className="size-4" />, text: 'Who owns the open action items from the design handoff meeting?' },
  { icon: <AlertTriangle className="size-4" />, text: 'What are the open customer escalations and their priority?' },
  { icon: <ShieldCheck className="size-4" />, text: 'What is the status of reliability qualification (HTOL)?' },
]
