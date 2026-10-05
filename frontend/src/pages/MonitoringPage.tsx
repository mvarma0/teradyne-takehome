import { AlertOctagon, AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { BarTrend, ChartCard, LineTrend, StatTile } from '../components/charts'
import { Badge, Button, Card, cn, ErrorBanner, PageHeader, Spinner } from '../components/ui'
import { ms, pct } from '../lib/format'
import type { MetricsRollup, MetricsSummary } from '../types'

const WINDOWS = ['24h', '7d', '30d']

type RateKey = keyof Pick<MetricsRollup, 'answer_rate' | 'mean_confidence' | 'citation_valid_ratio' | 'negative_feedback_rate' | 'mean_top_semantic'>

export default function MonitoringPage() {
  const [window, setWindow] = useState('24h')
  const [data, setData] = useState<MetricsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api
      .metrics(window)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [window])
  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [load])

  const c = data?.current
  const b = data?.baseline
  const alerted = new Set(data?.alerts.map((a) => a.metric))
  const rateDelta = (k: RateKey) =>
    c?.[k] != null && b?.[k] != null && (b?.knowledge_queries ?? 0) > 0 ? (c[k] as number) - (b[k] as number) : null
  const pts = (d: number | null) => (d === null ? undefined : `${Math.abs(d * 100).toFixed(1)} pts`)
  const label = (bucket: string) =>
    window === '24h' ? `${bucket.slice(11, 13)}:00` : new Date(`${bucket}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const series = data?.timeseries ?? []
  const latencyDelta = c?.p95_latency_ms != null && b?.p95_latency_ms != null ? c.p95_latency_ms - b.p95_latency_ms : null

  return (
    <>
      <PageHeader
        title="Monitoring"
        subtitle="Answer quality signals compared with the previous window, to catch degradation before users notice."
        actions={
          <>
            <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 text-sm dark:border-slate-700 dark:bg-slate-900">
              {WINDOWS.map((w) => (
                <button
                  key={w}
                  onClick={() => setWindow(w)}
                  className={cn('rounded-md px-3 py-1', window === w ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900' : 'text-slate-600 dark:text-slate-400')}
                >
                  {w}
                </button>
              ))}
            </div>
            <Button variant="ghost" onClick={load} loading={loading}>
              <RefreshCw className="size-3.5" />
            </Button>
          </>
        }
      />
      <ErrorBanner error={error} />
      {!data && !error && <Spinner />}
      {data && c && (
        <div className="space-y-6">
          <AlertList summary={data} />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Answer rate" value={pct(c.answer_rate)} delta={rateDelta('answer_rate')} deltaText={pts(rateDelta('answer_rate'))} alert={alerted.has('answer_rate')} hint="Knowledge questions answered confidently (not routed)" />
            <StatTile label="Mean confidence" value={pct(c.mean_confidence)} delta={rateDelta('mean_confidence')} deltaText={pts(rateDelta('mean_confidence'))} alert={alerted.has('mean_confidence')} />
            <StatTile label="Citation validity" value={pct(c.citation_valid_ratio)} delta={rateDelta('citation_valid_ratio')} deltaText={pts(rateDelta('citation_valid_ratio'))} alert={alerted.has('citation_valid_ratio')} hint="Share of [n] markers pointing at a real retrieved excerpt" />
            <StatTile label="Negative feedback" value={pct(c.negative_feedback_rate)} delta={rateDelta('negative_feedback_rate')} deltaText={pts(rateDelta('negative_feedback_rate'))} goodWhen="down" alert={alerted.has('negative_feedback_rate')} hint="Thumbs down + rejections + corrections per knowledge question" />
            <StatTile label="p95 latency" value={ms(c.p95_latency_ms)} delta={latencyDelta} deltaText={latencyDelta === null ? undefined : ms(Math.abs(latencyDelta))} goodWhen="down" alert={alerted.has('p95_latency_ms')} />
            <StatTile label="Mean retrieval score" value={pct(c.mean_top_semantic)} delta={rateDelta('mean_top_semantic')} deltaText={pts(rateDelta('mean_top_semantic'))} hint="Top semantic similarity per query; drops signal content drift" />
            <Card className="p-4">
              <p className="text-xs text-slate-500">Volume</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{c.queries}</p>
              <p className="mt-1 text-xs text-slate-400">{c.knowledge_queries} knowledge questions · baseline {b?.queries ?? 0}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-slate-500">Guardrails</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{c.guardrail_blocks}</p>
              <p className="mt-1 flex flex-wrap gap-1 text-xs">
                <Badge tone="red">{c.guardrail_by_type.prompt_injection ?? 0} injection</Badge>
                <Badge tone="amber">{c.guardrail_by_type.off_topic ?? 0} off-topic</Badge>
                <Badge>{c.pii_redactions} PII</Badge>
              </p>
            </Card>
          </div>

          {series.length === 0 ? (
            <Card className="p-8 text-center text-sm text-slate-500">No traffic in this window yet. Ask a few questions in Chat.</Card>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              <ChartCard title="Answer rate" subtitle="Share of knowledge questions answered confidently">
                <LineTrend data={series} xKey="bucket" series={[{ key: 'answer_rate', label: 'Answer rate', color: 'var(--series-1)' }]} format={(v) => pct(v)} domain={[0, 1]} labelFormat={label} />
              </ChartCard>
              <ChartCard title="Mean confidence" subtitle="Average answer confidence per period">
                <LineTrend data={series} xKey="bucket" series={[{ key: 'mean_confidence', label: 'Mean confidence', color: 'var(--series-1)' }]} format={(v) => pct(v)} domain={[0, 1]} labelFormat={label} />
              </ChartCard>
              <ChartCard title="Queries" subtitle="All questions, including guardrail-handled ones">
                <BarTrend data={series} xKey="bucket" series={{ key: 'queries', label: 'Queries', color: 'var(--series-1)' }} format={(v) => String(v ?? 0)} labelFormat={label} />
              </ChartCard>
              <ChartCard title="p95 latency" subtitle="End-to-end response time">
                <LineTrend data={series} xKey="bucket" series={[{ key: 'p95_latency_ms', label: 'p95 latency', color: 'var(--series-1)' }]} format={(v) => ms(v)} domain={[0, Math.max(1000, ...series.map((s) => s.p95_latency_ms ?? 0)) * 1.1]} labelFormat={label} />
              </ChartCard>
            </div>
          )}

          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr className="border-b border-slate-100 dark:border-slate-800">
                  <th className="px-4 py-2 font-medium">Signal</th>
                  <th className="px-4 py-2 font-medium">Current</th>
                  <th className="px-4 py-2 font-medium">Previous window</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['Routed (low confidence)', pct(c.routed_rate), pct(b?.routed_rate)],
                  ['Low-confidence gaps', c.low_confidence_gaps, b?.low_confidence_gaps],
                  ['Rejections', c.rejections, b?.rejections],
                  ['Corrections', c.corrections, b?.corrections],
                  ['Thumbs up / down', `${c.feedback_up} / ${c.feedback_down}`, `${b?.feedback_up ?? 0} / ${b?.feedback_down ?? 0}`],
                  ['Uncited statements removed', c.uncited_dropped, b?.uncited_dropped],
                  ['p50 latency / first token', `${ms(c.p50_latency_ms)} / ${ms(c.p50_first_token_ms)}`, `${ms(b?.p50_latency_ms)} / ${ms(b?.p50_first_token_ms)}`],
                  ['Mean rerank score (0-10)', c.mean_top_rerank ?? '—', b?.mean_top_rerank ?? '—'],
                ].map(([k, v1, v2]) => (
                  <tr key={String(k)} className="border-b border-slate-50 last:border-0 dark:border-slate-800/60">
                    <td className="px-4 py-2 text-slate-600 dark:text-slate-300">{k}</td>
                    <td className="px-4 py-2 font-medium tabular-nums">{String(v1 ?? '—')}</td>
                    <td className="px-4 py-2 text-slate-500 tabular-nums">{String(v2 ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </>
  )
}

function AlertList({ summary }: { summary: MetricsSummary }) {
  if (summary.alerts.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
        <CheckCircle2 className="size-4" />
        {summary.current.knowledge_queries < 5
          ? 'Healthy: not enough traffic for alerting yet (needs 5+ knowledge questions).'
          : 'Healthy: all quality signals within thresholds.'}
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {summary.alerts.map((a) => (
        <div
          key={a.metric + a.message}
          className={cn(
            'flex items-start gap-2 rounded-xl border px-4 py-2.5 text-sm',
            a.severity === 'critical'
              ? 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300'
              : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300',
          )}
        >
          {a.severity === 'critical' ? <AlertOctagon className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
          <div>
            <span className="font-medium capitalize">{a.severity}:</span> {a.message}
            <span className="ml-1 text-xs opacity-80">
              ({a.metric} = {a.value < 2 ? pct(a.value, 1) : a.value}, threshold {a.threshold < 2 ? pct(a.threshold, 1) : a.threshold})
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
