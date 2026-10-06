import {
  AlertTriangle,
  ArrowUp,
  Check,
  Copy,
  Filter,
  GitBranch,
  Pencil,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { fileName, getUserName, initials, label, ms } from '../lib/format'
import type { AnswerPayload, Citation, DocumentMeta, QueryFilters, Routing } from '../types'
import { AnswerMarkdown, EvidenceRail } from './citations'
import { ConfidenceMeter, PriorityBadge, TopicBadge } from './meta'
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
    <div className="border-t border-slate-200/80 pt-6 first:border-t-0 first:pt-0 dark:border-slate-800">
      <p className="max-w-[68ch] text-lg leading-snug font-semibold tracking-tight whitespace-pre-wrap text-slate-900 dark:text-slate-50">
        {text}
      </p>
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
  const [active, setActive] = useState<number | null>(null)
  const cited = new Set(p?.cited ?? [])
  const blocked = guardCategory === 'prompt_injection' || guardCategory === 'off_topic'
  const knowledge = guardCategory === 'knowledge_question' || (!guardCategory && citations.length > 0)
  const showRail = knowledge && citations.length > 0 && !blocked

  return (
    // The sources column is always reserved on wide screens so the answer never reflows when sources arrive.
    <div className="grid gap-x-12 gap-y-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-4">
        {msg.streaming && msg.stage && !text && (
          <div className="flex items-center gap-2 text-sm text-slate-500" role="status">
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
          <div className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-400">
            <ShieldAlert className="size-4" />
            {guardCategory === 'prompt_injection' ? 'Blocked: this looks like a prompt-injection attempt' : 'Outside what the knowledge base covers'}
          </div>
        )}

        {msg.error ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
            {msg.error}
          </div>
        ) : (
          (text || msg.streaming) && (
            <AnswerMarkdown
              text={text}
              citations={citations}
              onOpen={onOpenCitation}
              streaming={msg.streaming && !!text}
              active={active}
              onHover={setActive}
            />
          )
        )}

        {p && p.status !== 'refused' && p.status !== 'blocked' && guardCategory === 'knowledge_question' && (
          <>
            <AnswerMeta payload={p} threshold={threshold} />
            {p.dropped_claims.length > 0 && (
              <p className="flex items-center gap-1.5 text-xs text-slate-500">
                <ShieldCheck className="size-3.5 text-brand-600" />
                {p.dropped_claims.length} statement{p.dropped_claims.length > 1 && 's'} removed because no source supported{' '}
                {p.dropped_claims.length > 1 ? 'them' : 'it'}
              </p>
            )}
            {(p.routing?.length ?? 0) > 0 && <RoutingPanel routing={p.routing} confident={p.confident} />}
            <FeedbackBar payload={p} onPatch={onPatch} />
          </>
        )}
      </div>

      {showRail ? (
        <div className="lg:sticky lg:top-0 lg:max-h-[calc(100vh-12rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
          <EvidenceRail citations={citations} cited={cited} active={active} onHover={setActive} onOpen={onOpenCitation} />
        </div>
      ) : (
        msg.streaming &&
        !blocked && (
          <div className="hidden space-y-2 self-start lg:block" aria-hidden>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800/60" />
            ))}
          </div>
        )
      )}
    </div>
  )
}

const PRIORITY_RANK = ['none', 'low', 'medium', 'high', 'critical']

function AnswerMeta({ payload: p, threshold }: { payload: AnswerPayload; threshold: number }) {
  const citedDocs = new Set(p.citations.filter((c) => p.cited?.includes(c.n)).map((c) => c.doc_id))
  // Metadata describes the sources the answer actually cites; nothing cited, nothing shown.
  const docs = p.documents.filter((d) => citedDocs.has(d.doc_id))
  const topics = [...new Set(docs.map((d) => d.topic_domain).filter(Boolean))] as string[]
  const priority = docs.map((d) => d.priority ?? 'none').sort((a, b) => PRIORITY_RANK.indexOf(b) - PRIORITY_RANK.indexOf(a))[0]
  const products = [...new Set(docs.flatMap((d) => d.products))]
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-200/80 pt-3 text-xs text-slate-500 dark:border-slate-800">
      <ConfidenceMeter value={p.confidence} threshold={threshold} />
      {p.status === 'rejected' && <Badge tone="red">Rejected</Badge>}
      {p.status === 'corrected' && <Badge tone="blue">Corrected</Badge>}
      {(p.guardrails?.pii_redactions ?? 0) > 0 && <Badge tone="slate">Personal data redacted</Badge>}
      <div className="flex flex-wrap items-center gap-1">
        {topics.map((t) => (
          <TopicBadge key={t} topic={t} />
        ))}
        <PriorityBadge priority={priority} />
        {products.slice(0, 3).map((x) => (
          <Badge key={x} tone="brand">
            {x}
          </Badge>
        ))}
      </div>
      <span className="ml-auto flex items-center gap-3">
        <Link to={`/trace/${p.query_id}`} className="inline-flex items-center gap-1 text-slate-500 hover:text-brand-700 dark:hover:text-brand-200" title="See how this answer was built">
          <GitBranch className="size-3.5" /> Trace
        </Link>
        <span className="tabular-nums text-slate-400" title="Time to the validated answer">
          {ms(p.latency_ms)}
        </span>
      </span>
    </div>
  )
}

export function RoutingPanel({ routing, confident }: { routing: Routing[]; confident: boolean | null }) {
  return (
    <section className="rounded-lg border border-amber-300/70 bg-amber-50/70 p-4 dark:border-amber-800/70 dark:bg-amber-950/20">
      <div className="mb-3 flex items-start gap-2.5">
        <UserRound className="mt-0.5 size-4 shrink-0 text-amber-700 dark:text-amber-400" />
        <div>
          <h3 className="text-sm font-semibold text-amber-950 dark:text-amber-100">
            {confident === false ? 'Not confident enough to answer. Ask someone who knows' : 'People who can confirm this'}
          </h3>
          <p className="text-xs text-amber-900/80 dark:text-amber-200/70">
            Chosen from the authors and attendees of the closest matching sources. Edit the draft, then send.
          </p>
        </div>
      </div>
      <div className="space-y-2">
        {routing.map((r) => (
          <RoutingCard key={r.routing_id ?? r.id ?? r.person} routing={r} />
        ))}
      </div>
    </section>
  )
}

function RoutingCard({ routing }: { routing: Routing }) {
  const id = routing.routing_id ?? routing.id
  const [question, setQuestion] = useState(routing.edited_question ?? routing.draft_question)
  const [status, setStatus] = useState(routing.status ?? 'suggested')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const send = async () => {
    if (!id) return
    setBusy(true)
    try {
      const r = await api.sendRouting(id, question, getUserName() || undefined)
      setStatus(r.status ?? 'sent')
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
    <div className="rounded-md border border-amber-200/80 bg-white p-3 dark:border-slate-700 dark:bg-[#121a1d]">
      <div className="flex items-start gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-xs font-semibold text-white dark:bg-slate-200 dark:text-slate-900">
          {initials(routing.person)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-semibold">{routing.person}</span>
            {routing.role && <span className="text-xs text-slate-500">{routing.role}</span>}
            {status === 'sent' && (
              <Badge tone="green">
                <Check className="size-3" /> Sent
              </Badge>
            )}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{routing.reason}</p>
          {routing.matched_sources?.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {routing.matched_sources.map((s) => (
                <span
                  key={s.source_file}
                  title={s.snippet}
                  className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px] text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                >
                  {fileName(s.source_file)}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <label className="mt-3 block">
        <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
          {status === 'sent' ? 'Question sent' : 'Draft question'}
        </span>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
          disabled={status === 'sent'}
          className={cn(inputClass, 'resize-y text-[13px] leading-relaxed disabled:bg-slate-50 dark:disabled:bg-slate-800/60')}
        />
      </label>
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
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? 'Copied' : 'Copy'}
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
    <div className="rounded-xl border border-slate-300/80 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_8px_24px_-12px_rgb(15_23_42/0.12)] transition-colors focus-within:border-brand-500 dark:border-slate-700 dark:bg-[#121a1d] dark:shadow-none">
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
                {label(t)}
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
                {label(p)}
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
          aria-label="Filters"
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
          placeholder="Ask about decisions, yield, test, reliability, customers…"
          aria-label="Question"
          className="max-h-[200px] flex-1 resize-none bg-transparent py-2 text-sm outline-none placeholder:text-slate-400 focus-visible:outline-none"
        />
        {disabled && onStop ? (
          <button onClick={onStop} className="rounded-lg bg-slate-200 p-2 text-slate-700 dark:bg-slate-700 dark:text-slate-200" title="Stop">
            <span className="block size-4 rounded-sm bg-current p-1" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim()}
            className="rounded-lg bg-brand-600 p-2 text-white transition-colors hover:bg-brand-700 disabled:bg-slate-300 dark:disabled:bg-slate-700"
            title="Send"
            aria-label="Send"
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
