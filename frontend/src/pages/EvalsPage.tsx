import { Check, ChevronDown, FlaskConical, Play, Wand2, X } from 'lucide-react'
import { Fragment, useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { ChartCard, LineTrend } from '../components/charts'
import { Badge, Button, Card, cn, EmptyState, ErrorBanner, inputClass, PageHeader, Spinner } from '../components/ui'
import { fileName, ms, num, pct, relativeTime } from '../lib/format'
import type { EvalRun, EvalSummary } from '../types'

const METRICS: { key: keyof EvalSummary; label: string; hint: string; target?: number }[] = [
  { key: 'hit_rate', label: 'Retrieval hit rate', hint: 'An expected source is among retrieved excerpts', target: 0.8 },
  { key: 'mrr', label: 'MRR', hint: 'Mean reciprocal rank of the first expected source' },
  { key: 'cited_expected_rate', label: 'Cited expected source', hint: 'Answer actually cites an expected source' },
  { key: 'faithfulness', label: 'Faithfulness', hint: 'LLM judge: answer supported by cited excerpts', target: 0.7 },
  { key: 'relevance', label: 'Answer relevance', hint: 'LLM judge: answer addresses the question' },
  { key: 'keyword_recall', label: 'Keyword recall', hint: 'Expected key facts present in the answer' },
  { key: 'answerability_accuracy', label: 'Answerability', hint: 'Confident when answerable, abstains/routes when not', target: 0.7 },
  { key: 'citation_valid_ratio', label: 'Citation validity', hint: 'Share of [n] markers pointing at real excerpts' },
]

export default function EvalsPage() {
  const [runs, setRuns] = useState<EvalRun[] | null>(null)
  const [datasets, setDatasets] = useState<Record<string, number | string>>({})
  const [selected, setSelected] = useState<EvalRun | null>(null)
  const [dataset, setDataset] = useState('golden')
  const [n, setN] = useState(15)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const r = await api.evals()
    setRuns(r.runs)
    setDatasets(r.datasets)
    return r.runs
  }, [])

  const select = useCallback(async (id: string) => setSelected(await api.evalRun(id)), [])

  useEffect(() => {
    load()
      .then((r) => r[0] && select(r[0].id))
      .catch((e) => setError(e.message))
  }, [load, select])

  // Poll while a run is in progress.
  const running = runs?.some((r) => r.status === 'running')
  useEffect(() => {
    if (!running) return
    const t = setInterval(async () => {
      const r = await load()
      const current = r.find((x) => x.id === selected?.id) ?? r[0]
      if (current) select(current.id)
    }, 4000)
    return () => clearInterval(t)
  }, [running, load, select, selected?.id])

  const start = async () => {
    setBusy('run')
    setError(null)
    try {
      const { run_id } = await api.startEval(dataset)
      await load()
      await select(run_id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  const synth = async () => {
    setBusy('synth')
    setError(null)
    try {
      await api.synthesize(n)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const completed = (runs ?? []).filter((r) => r.status === 'completed' && r.summary).reverse()
  const rate = (v: number | null | undefined) => (v === null || v === undefined ? null : Math.max(0, Math.min(1, v)))
  const trend = completed.map((r) => ({
    run: r.started_at,
    hit_rate: rate(r.summary?.hit_rate),
    faithfulness: rate(r.summary?.faithfulness),
    answerability_accuracy: rate(r.summary?.answerability_accuracy),
  }))

  return (
    <>
      <PageHeader
        title="Evals"
        subtitle="Offline quality checks: retrieval, grounding and answerability on golden and synthetic question sets."
        actions={
          <>
            <select value={dataset} onChange={(e) => setDataset(e.target.value)} className={`${inputClass} w-auto!`}>
              <option value="golden">Golden ({datasets.golden ?? 0})</option>
              <option value="synthetic">Synthetic ({datasets.synthetic ?? 0})</option>
              <option value="all">All</option>
            </select>
            <Button variant="primary" onClick={start} loading={busy === 'run'} disabled={!!running}>
              <Play className="size-3.5" /> Run eval
            </Button>
          </>
        }
      />
      <ErrorBanner error={error} />

      <Card className="mb-6 flex flex-wrap items-center gap-3 p-4 text-sm">
        <Wand2 className="size-4 text-violet-500" />
        <span className="flex-1 text-slate-600 dark:text-slate-300">
          Generate a synthetic set: the LLM writes one question per sampled document chunk, and that chunk's file becomes the expected source.
        </span>
        <input type="number" min={1} max={100} value={n} onChange={(e) => setN(Number(e.target.value))} className={`${inputClass} w-20!`} />
        <Button onClick={synth} loading={busy === 'synth'}>
          Generate
        </Button>
      </Card>

      {!runs && !error && <Spinner />}
      {runs?.length === 0 && (
        <EmptyState icon={<FlaskConical className="size-10" />} title="No eval runs yet">
          Run the golden set to measure retrieval and answer quality for the current configuration.
        </EmptyState>
      )}

      {runs && runs.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <div className="space-y-2">
            <h3 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Runs</h3>
            {runs.map((r) => (
              <button
                key={r.id}
                onClick={() => select(r.id)}
                className={cn(
                  'w-full rounded-xl border p-3 text-left text-sm transition',
                  selected?.id === r.id
                    ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-700/10'
                    : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium capitalize">{r.dataset}</span>
                  <Badge tone={r.status === 'completed' ? 'green' : r.status === 'failed' ? 'red' : 'blue'}>{r.status}</Badge>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {relativeTime(r.started_at)}
                  {r.summary && ` · hit ${pct(r.summary.hit_rate)} · faith ${pct(r.summary.faithfulness)}`}
                  {r.status === 'running' && ` · ${r.done ?? 0} done`}
                </p>
              </button>
            ))}
          </div>

          <div className="min-w-0 space-y-6">
            {trend.length >= 2 && (
              <ChartCard
                title="Quality across runs"
                subtitle="Completed runs, oldest to newest"
                legend={[
                  { key: 'hit_rate', label: 'Hit rate', color: 'var(--series-1)' },
                  { key: 'faithfulness', label: 'Faithfulness', color: 'var(--series-2)' },
                  { key: 'answerability_accuracy', label: 'Answerability', color: 'var(--series-3)' },
                ]}
              >
                <LineTrend
                  data={trend}
                  xKey="run"
                  series={[
                    { key: 'hit_rate', label: 'Hit rate', color: 'var(--series-1)' },
                    { key: 'faithfulness', label: 'Faithfulness', color: 'var(--series-2)' },
                    { key: 'answerability_accuracy', label: 'Answerability', color: 'var(--series-3)' },
                  ]}
                  format={(v) => pct(v)}
                  domain={[0, 1]}
                  labelFormat={(l) => new Date(l).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                />
              </ChartCard>
            )}
            {selected && <RunDetail run={selected} />}
          </div>
        </div>
      )}
    </>
  )
}

function RunDetail({ run }: { run: EvalRun }) {
  const [open, setOpen] = useState<string | null>(null)
  const s = run.summary
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="font-medium capitalize">{run.dataset} run</h3>
            <p className="text-xs text-slate-500">
              {new Date(run.started_at).toLocaleString()}
              {run.config && ` · ${run.config.llm} · ${run.config.embeddings} · reranker ${run.config.reranker} · top_k ${run.config.top_k}`}
            </p>
          </div>
          {run.status === 'running' && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> {run.results?.length ?? 0} / {run.total ?? '?'} cases
            </div>
          )}
        </div>
        {run.error && <p className="mt-2 text-sm text-rose-600">{run.error}</p>}
        {s && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {METRICS.map((m) => {
              const v = s[m.key] as number | null
              const below = m.target !== undefined && v !== null && v < m.target
              return (
                <div key={m.key} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50" title={m.hint}>
                  <p className="text-xs text-slate-500">{m.label}</p>
                  <p className={cn('mt-0.5 text-xl font-semibold tabular-nums', below && 'text-rose-600 dark:text-rose-400')}>
                    {m.key === 'mrr' ? num(v) : pct(v)}
                  </p>
                  {m.target !== undefined && <p className="text-[11px] text-slate-400">target ≥ {pct(m.target)}</p>}
                </div>
              )
            })}
          </div>
        )}
        {s && (
          <p className="mt-3 text-xs text-slate-500">
            {s.cases} cases · mean confidence {pct(s.mean_confidence)} · unanswerable abstention {pct(s.unanswerable_refusal_rate)} · p50 latency {ms(s.p50_latency_ms)}
          </p>
        )}
      </Card>

      {run.results && run.results.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <th className="px-3 py-2 font-medium">Question</th>
                <th className="px-2 py-2 font-medium">Hit</th>
                <th className="px-2 py-2 font-medium">RR</th>
                <th className="px-2 py-2 font-medium">Cited</th>
                <th className="px-2 py-2 font-medium">Answerable</th>
                <th className="px-2 py-2 font-medium">Keywords</th>
                <th className="px-2 py-2 font-medium">Faith.</th>
                <th className="px-2 py-2 font-medium">Conf.</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {run.results.map((r) => (
                <Fragment key={r.case_id}>
                  <tr className="cursor-pointer border-b border-slate-50 hover:bg-slate-50 dark:border-slate-800/60 dark:hover:bg-slate-800/40" onClick={() => setOpen(open === r.case_id ? null : r.case_id)}>
                    <td className="max-w-[320px] px-3 py-2">
                      <span className="mr-1.5 font-mono text-[11px] text-slate-400">{r.case_id}</span>
                      {r.question}
                    </td>
                    <td className="px-2 py-2"><Mark ok={r.hit} /></td>
                    <td className="px-2 py-2 tabular-nums">{num(r.reciprocal_rank)}</td>
                    <td className="px-2 py-2"><Mark ok={r.cited_expected} /></td>
                    <td className="px-2 py-2">
                      <span className="flex items-center gap-1">
                        <Mark ok={r.answerability_correct} />
                        <span className="text-[11px] text-slate-400">{r.answerable ? 'yes' : 'no'}</span>
                      </span>
                    </td>
                    <td className="px-2 py-2 tabular-nums">{pct(r.keyword_recall)}</td>
                    <td className="px-2 py-2 tabular-nums">{pct(r.faithfulness)}</td>
                    <td className="px-2 py-2 tabular-nums">{pct(r.confidence)}</td>
                    <td className="px-2 py-2"><ChevronDown className={cn('size-4 text-slate-400 transition', open === r.case_id && 'rotate-180')} /></td>
                  </tr>
                  {open === r.case_id && (
                    <tr className="bg-slate-50/70 dark:bg-slate-950/30">
                      <td colSpan={9} className="space-y-2 px-3 py-3 text-xs">
                        <p><span className="font-medium">Answer:</span> {r.answer}</p>
                        {r.expected.expected_sources && <p><span className="font-medium">Expected:</span> {r.expected.expected_sources.map(fileName).join(', ')} · keywords {r.expected.expected_keywords?.join(', ')}</p>}
                        <p><span className="font-medium">Retrieved:</span> {[...new Set(r.retrieved.map(fileName))].join(', ') || 'none'}</p>
                        {r.judge_reason && <p><span className="font-medium">Judge:</span> {r.judge_reason}</p>}
                        <p className="text-slate-500">status {r.status} · {ms(r.latency_ms)}</p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function Mark({ ok }: { ok: boolean | null | undefined }) {
  if (ok === null || ok === undefined) return <span className="text-slate-300">—</span>
  return ok ? <Check className="size-4 text-emerald-600" aria-label="pass" /> : <X className="size-4 text-rose-500" aria-label="fail" />
}
