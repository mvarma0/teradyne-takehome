import { FileStack, RefreshCw, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { MetaBadges, SOURCE_LABEL, SourceIcon } from '../components/meta'
import { Badge, Button, Card, EmptyState, ErrorBanner, inputClass, PageHeader, Spinner } from '../components/ui'
import { displayTitle, label, peopleLabel } from '../lib/format'
import type { DocumentMeta, Stats } from '../types'

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentMeta[] | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [type, setType] = useState('')
  const [topic, setTopic] = useState('')
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ingesting, setIngesting] = useState(false)
  const [report, setReport] = useState<Record<string, unknown> | null>(null)

  const load = () => {
    api.documents().then(setDocs).catch((e) => setError(e.message))
    api.stats().then(setStats).catch(() => {})
  }
  useEffect(load, [])

  const ingest = async (force: boolean) => {
    setIngesting(true)
    setError(null)
    try {
      setReport(await api.ingest(force))
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setIngesting(false)
    }
  }

  const topics = useMemo(() => [...new Set((docs ?? []).map((d) => d.topic_domain).filter(Boolean))] as string[], [docs])
  const filtered = (docs ?? []).filter((d) => {
    const q = query.toLowerCase()
    const people = [...d.attendees, ...d.authors].join(' ').toLowerCase()
    return (
      (!type || d.source_type === type) &&
      (!topic || d.topic_domain === topic) &&
      (!q || `${d.title} ${d.source_file} ${people} ${d.summary ?? ''}`.toLowerCase().includes(q))
    )
  })

  return (
    <>
      <PageHeader
        title="Documents"
        subtitle={
          stats
            ? `${stats.documents} sources indexed as ${stats.chunks} passages. Models: ${stats.llm} for answers, ${stats.embeddings} for search.`
            : 'Meetings and Office documents, with the metadata derived from each'
        }
        actions={
          <>
            <Button onClick={() => ingest(false)} loading={ingesting}>
              <RefreshCw className="size-3.5" /> Ingest changes
            </Button>
            <Button variant="ghost" onClick={() => ingest(true)} disabled={ingesting} title="Re-derive metadata and re-embed every file">
              Re-ingest all
            </Button>
          </>
        }
      />
      <ErrorBanner error={error} />
      {report && (
        <Card className="mb-4 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-medium">Last ingest:</span>
            <span>{String(report.files_found)} files</span>
            <span>{String(report.ingested)} ingested</span>
            <span>{String(report.skipped_unchanged)} unchanged</span>
            <span>{String(report.chunks_written)} chunks</span>
            <span>{String(report.duration_s)}s</span>
            {(report.failed as unknown[]).length > 0 && <Badge tone="red">{(report.failed as unknown[]).length} failed</Badge>}
          </div>
          {(report.warnings as string[]).length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-amber-700 dark:text-amber-400">
              {(report.warnings as string[]).slice(0, 8).map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute top-2.5 left-3 size-4 text-slate-400" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search title, people, summary…" className={`${inputClass} pl-9`} />
        </div>
        <select value={type} onChange={(e) => setType(e.target.value)} className={`${inputClass} w-auto!`}>
          <option value="">All types</option>
          {Object.entries(SOURCE_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
              {stats?.by_type[k] ? ` (${stats.by_type[k]})` : ''}
            </option>
          ))}
        </select>
        <select value={topic} onChange={(e) => setTopic(e.target.value)} className={`${inputClass} w-auto!`}>
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>
              {label(t)}
            </option>
          ))}
        </select>
      </div>

      {!docs && !error && <Spinner />}
      {docs && filtered.length === 0 && (
        <EmptyState icon={<FileStack className="size-10" />} title={docs.length ? 'No matching documents' : 'Nothing ingested yet'}>
          {!docs.length && 'Run an ingest to load data/meetings and data/documents.'}
        </EmptyState>
      )}
      {docs && filtered.length > 0 && (
        <Card className="overflow-hidden">
          <div className="hidden grid-cols-[minmax(0,1fr)_200px_92px] gap-6 border-b border-slate-200/80 bg-slate-50/70 px-4 py-2 text-xs font-medium text-slate-500 md:grid dark:border-slate-800 dark:bg-slate-900/40">
            <span>Source</span>
            <span>People</span>
            <span className="text-right">Date</span>
          </div>
          <ul className="divide-y divide-slate-200/80 dark:divide-slate-800">
            {filtered.map((d) => {
              const people = d.source_type === 'meeting' ? d.attendees : d.authors
              return (
                <li key={d.doc_id}>
                  <Link
                    to={`/documents/${d.doc_id}`}
                    className="grid gap-x-6 gap-y-2 px-4 py-3.5 transition-colors hover:bg-slate-50 md:grid-cols-[minmax(0,1fr)_200px_92px] dark:hover:bg-slate-800/40"
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <SourceIcon type={d.source_type} className="mt-0.5 size-[18px] shrink-0" />
                      <div className="min-w-0 space-y-1">
                        <p className="truncate text-sm font-medium">{displayTitle(d.title, d.source_file)}</p>
                        <p className="truncate font-mono text-[11px] text-slate-500">{d.source_file}</p>
                        <MetaBadges topic={d.topic_domain} priority={d.priority} products={d.products} />
                      </div>
                    </div>
                    <p className="line-clamp-2 pl-[30px] text-xs leading-relaxed text-slate-600 md:pl-0 dark:text-slate-400">
                      <span className="text-slate-500 md:hidden">{peopleLabel(d.source_type, people.length)} </span>
                      {people.length ? people.join(', ') : <span className="text-slate-400">No author recorded</span>}
                    </p>
                    <p className="pl-[30px] text-xs text-slate-500 tabular-nums md:pl-0 md:text-right">
                      {d.date ?? <span className="text-slate-400">undated</span>}
                    </p>
                  </Link>
                </li>
              )
            })}
          </ul>
        </Card>
      )}
    </>
  )
}
