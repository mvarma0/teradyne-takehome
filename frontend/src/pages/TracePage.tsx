import { Check, GitBranch, MessageSquare, Minus, Search } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ConfidenceMeter, SourceIcon } from '../components/meta'
import { Badge, Card, cn, EmptyState, ErrorBanner, inputClass, PageHeader, Spinner, type Tone } from '../components/ui'
import { displayTitle, fileName, label, ms, num, relativeTime } from '../lib/format'
import type { Trace, TraceSummary } from '../types'

const STATUS_TONE: Record<string, Tone> = {
  answered: 'green',
  routed: 'amber',
  rejected: 'red',
  corrected: 'blue',
  refused: 'slate',
  blocked: 'red',
}

export default function TracePage() {
  const { queryId } = useParams()
  const navigate = useNavigate()
  const [items, setItems] = useState<TraceSummary[] | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .traces()
      .then((t) => {
        setItems(t)
        if (!queryId && t.length) navigate(`/trace/${t[0].id}`, { replace: true })
      })
      .catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const q = filter.toLowerCase()
  const shown = (items ?? []).filter(
    (t) => !q || `${t.query_text} ${t.cited_files.join(' ')} ${t.status}`.toLowerCase().includes(q),
  )

  return (
    <>
      <PageHeader
        title="Traceability"
        subtitle="Follow any answer back through each step: the question, what was searched, which passages were retrieved and cited, how confident it was, and where it went next."
      />
      <ErrorBanner error={error} />
      {!items && !error && <Spinner />}
      {items && items.length === 0 && (
        <EmptyState icon={<GitBranch className="size-10" />} title="No questions traced yet">
          Ask something on the <Link to="/chat" className="text-brand-700 underline dark:text-brand-200">Ask</Link> page. Every answer
          is recorded here.
        </EmptyState>
      )}
      {items && items.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-2 lg:sticky lg:top-0 lg:self-start">
            <div className="relative">
              <Search className="absolute top-2.5 left-3 size-4 text-slate-400" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter questions or files…"
                className={`${inputClass} pl-9`}
              />
            </div>
            <Card className="max-h-[70vh] overflow-y-auto">
              <ul className="divide-y divide-slate-200/80 dark:divide-slate-800">
                {shown.map((t) => (
                  <li key={t.id}>
                    <Link
                      to={`/trace/${t.id}`}
                      className={cn(
                        'block px-3 py-2.5 transition-colors',
                        t.id === queryId ? 'bg-brand-50 dark:bg-brand-900/30' : 'hover:bg-slate-50 dark:hover:bg-slate-800/40',
                      )}
                    >
                      <p className="line-clamp-2 text-sm font-medium">{t.query_text}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
                        <Badge tone={STATUS_TONE[t.status] ?? 'slate'}>{label(t.status)}</Badge>
                        {t.n_retrieved > 0 && (
                          <span>
                            {t.n_cited}/{t.n_retrieved} cited
                          </span>
                        )}
                        {t.n_gaps > 0 && <span className="text-amber-700 dark:text-amber-400">{t.n_gaps} gap</span>}
                        <span className="ml-auto">{relativeTime(t.created_at)}</span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <div className="min-w-0">{queryId ? <TraceDetail id={queryId} /> : null}</div>
        </div>
      )}
    </>
  )
}

function TraceDetail({ id }: { id: string }) {
  const [t, setT] = useState<Trace | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setT(null)
    setError(null)
    api.trace(id).then(setT).catch((e) => setError(e.message))
  }, [id])
  if (error) return <ErrorBanner error={error} />
  if (!t) return <Spinner />

  const cited = new Set(t.cited ?? [])
  const knowledge = t.guardrails?.category === 'knowledge_question'
  const rewritten = t.standalone_query && t.standalone_query !== t.query
  const comps = t.confidence_detail?.components ?? {}

  return (
    <ol className="relative space-y-4 border-l border-slate-200 pl-6 dark:border-slate-800">
      <Step n={1} title="Question asked">
        <p className="text-base font-semibold">{t.query}</p>
        <p className="mt-1 text-xs text-slate-500">
          {new Date(t.created_at).toLocaleString()} · query id <span className="font-mono">{t.id}</span>
          {t.conversation_id && (
            <>
              {' · '}
              <Link to={`/chat/${t.conversation_id}`} className="inline-flex items-center gap-1 text-brand-700 hover:underline dark:text-brand-200">
                <MessageSquare className="size-3" /> open conversation
              </Link>
            </>
          )}
        </p>
        {t.filters && Object.values(t.filters).some(Boolean) && (
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(t.filters)
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <Badge key={k} tone="outline">
                  {label(k)}: {String(v)}
                </Badge>
              ))}
          </div>
        )}
      </Step>

      <Step n={2} title="Guardrail check">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={knowledge ? 'green' : 'amber'}>{label(t.guardrails?.category)}</Badge>
          <span className="text-xs text-slate-500">via {t.guardrails?.method}</span>
        </div>
        {t.guardrails?.reason && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{t.guardrails.reason}</p>}
        {!knowledge && <p className="mt-1 text-xs text-slate-500">Not a knowledge question, so nothing was searched.</p>}
      </Step>

      {knowledge && (
        <>
          <Step n={3} title="Search query">
            {rewritten ? (
              <p className="text-sm">
                Follow-up rewritten using the chat history: <span className="font-medium">“{t.standalone_query}”</span>
              </p>
            ) : (
              <p className="text-sm text-slate-600 dark:text-slate-400">Searched as asked (no rewrite needed).</p>
            )}
          </Step>

          <Step n={4} title={`Retrieved ${t.citations.length} passages, ${cited.size} cited in the answer`}>
            {t.retrieval && (
              <p className="mb-2 text-xs text-slate-500">
                {t.retrieval.semantic_candidates} semantic + {t.retrieval.bm25_candidates} keyword candidates → {t.retrieval.fused_candidates} after
                fusion → reranked by {t.retrieval.reranker}
              </p>
            )}
            <Card className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50/70 text-slate-500 dark:bg-slate-900/40">
                  <tr>
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">Source</th>
                    <th className="px-3 py-2 font-medium">People</th>
                    <th className="px-3 py-2 text-right font-medium" title="Semantic similarity">Sem.</th>
                    <th className="px-3 py-2 text-right font-medium" title="BM25 keyword score">BM25</th>
                    <th className="px-3 py-2 text-right font-medium" title="LLM relevance 0-10">Rerank</th>
                    <th className="px-3 py-2 text-center font-medium">Cited</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200/80 dark:divide-slate-800">
                  {t.citations.map((c) => (
                    <tr key={c.chunk_id} className={cited.has(c.n) ? '' : 'text-slate-500'}>
                      <td className="px-3 py-2 tabular-nums">{c.n}</td>
                      <td className="max-w-[280px] px-3 py-2">
                        <Link to={`/documents/${c.doc_id}`} className="flex items-center gap-1.5 hover:underline" title={c.snippet}>
                          <SourceIcon type={c.source_type} className="size-3.5 shrink-0" />
                          <span className="truncate">{displayTitle(c.title, fileName(c.source_file))}</span>
                        </Link>
                        <p className="truncate font-mono text-[10.5px] text-slate-400">
                          {fileName(c.source_file)}
                          {c.section ? ` · ${c.section}` : ''}
                        </p>
                      </td>
                      <td className="max-w-[160px] truncate px-3 py-2" title={c.people.join(', ')}>
                        {c.people.join(', ') || '—'}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{num(c.scores.semantic)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{num(c.scores.bm25, 1)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{c.scores.rerank ?? '—'}</td>
                      <td className="px-3 py-2 text-center">
                        {cited.has(c.n) ? <Check className="mx-auto size-3.5 text-emerald-600" /> : <Minus className="mx-auto size-3.5 text-slate-300" />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </Step>

          <Step n={5} title="Answer and claim validation">
            <ul className="space-y-1.5 text-sm">
              {t.claims
                .filter((c) => c.kind === 'fact')
                .map((c, i) => (
                  <li key={i} className="flex gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
                    <span>
                      {plain(c.text)}{' '}
                      <span className="text-xs text-slate-500">[{c.citations.join(', ')}]</span>
                    </span>
                  </li>
                ))}
            </ul>
            {t.dropped_claims.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-medium text-slate-500">Removed: no retrieved passage supported these</p>
                <ul className="mt-1 space-y-1 text-sm text-slate-500 line-through decoration-rose-400/70">
                  {t.dropped_claims.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {(t.guardrails?.pii_redactions ?? 0) > 0 && (
              <p className="mt-2 text-xs text-slate-500">{t.guardrails.pii_redactions} personal-data item(s) redacted.</p>
            )}
          </Step>

          <Step n={6} title="Confidence">
            <ConfidenceMeter value={t.confidence} />
            {Object.keys(comps).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                {Object.entries(comps).map(([k, v]) => (
                  <span key={k}>
                    {label(k)} <span className="font-medium text-slate-700 tabular-nums dark:text-slate-300">{num(v)}</span>
                  </span>
                ))}
              </div>
            )}
            {(t.confidence_detail?.caps?.length ?? 0) > 0 && (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">Capped by: {t.confidence_detail!.caps.map(label).join(', ')}</p>
            )}
          </Step>
        </>
      )}

      <Step n={knowledge ? 7 : 3} title="Where it went">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={STATUS_TONE[t.status] ?? 'slate'}>{label(t.status)}</Badge>
          {t.feedback && <Badge tone={t.feedback === 'up' ? 'green' : 'red'}>Rated {t.feedback === 'up' ? 'helpful' : 'not helpful'}</Badge>}
          <span className="text-xs text-slate-500">answered in {ms(t.latency_ms)}</span>
        </div>
        {t.routing.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-slate-500">Routed to</p>
            {t.routing.map((r) => (
              <div key={r.routing_id ?? r.id ?? r.person} className="rounded-md border border-slate-200 p-2.5 text-sm dark:border-slate-800">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{r.person}</span>
                  {r.role && <span className="text-xs text-slate-500">{r.role}</span>}
                  <Badge tone={r.status === 'sent' ? 'green' : r.status === 'dismissed' ? 'slate' : 'amber'}>{label(r.status ?? 'suggested')}</Badge>
                  {r.sent_by && <span className="text-xs text-slate-500">by {r.sent_by}</span>}
                </div>
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{r.edited_question ?? r.draft_question}</p>
              </div>
            ))}
          </div>
        )}
        {t.gaps.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-slate-500">
              Captured in the <Link to="/review" className="text-brand-700 hover:underline dark:text-brand-200">review queue</Link>
            </p>
            {t.gaps.map((g) => (
              <div key={g.id} className="rounded-md border border-slate-200 p-2.5 text-sm dark:border-slate-800">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="amber">{label(g.type)}</Badge>
                  <Badge tone={g.review_status === 'pending' ? 'outline' : 'green'}>{label(g.review_status)}</Badge>
                  {g.submitted_by && <span className="text-xs text-slate-500">by {g.submitted_by}</span>}
                </div>
                {(g.correction_text || g.reason) && (
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{g.correction_text ?? g.reason}</p>
                )}
                {g.reviewer_note && <p className="mt-1 text-xs text-slate-500">Reviewer: {g.reviewer_note}</p>}
              </div>
            ))}
          </div>
        )}
        {t.routing.length === 0 && t.gaps.length === 0 && (
          <p className="mt-2 text-xs text-slate-500">Shown to the user; no routing or review needed.</p>
        )}
      </Step>
    </ol>
  )
}

// Claim text is markdown with [n] markers; show it as plain prose.
const plain = (text: string) =>
  text
    .replace(/\s*\[\d+(?:,\s*\d+)*\]/g, '')
    .replace(/\*\*|__/g, '')
    .replace(/\\([\\`*_{}[\]()#+\-.!])/g, '$1')
    .replace(/^\s*(?:[-*]|\d+\.)\s+/, '')

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="relative">
      <span className="absolute top-0.5 -left-[35px] flex size-5 items-center justify-center rounded-full border border-slate-300 bg-white text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-[#0f171a] dark:text-slate-300">
        {n}
      </span>
      <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-slate-500 uppercase">{title}</h3>
      {children}
    </li>
  )
}
