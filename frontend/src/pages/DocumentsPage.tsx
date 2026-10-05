import { FileStack, RefreshCw, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { MetaBadges, SOURCE_LABEL, SourceIcon } from '../components/meta'
import { Badge, Button, Card, EmptyState, ErrorBanner, inputClass, PageHeader, Spinner } from '../components/ui'
import { humanize } from '../lib/format'
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
            ? `${stats.documents} documents · ${stats.chunks} chunks · ${stats.embeddings} · ${stats.llm}`
            : 'Ingested meetings and Office documents with derived metadata'
        }
        actions={
          <>
            <Button onClick={() => ingest(false)} loading={ingesting}>
              <RefreshCw className="size-3.5" /> Ingest new / changed
            </Button>
            <Button variant="ghost" onClick={() => ingest(true)} disabled={ingesting} title="Re-enrich and re-embed everything">
              Force re-ingest
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
              {humanize(t)}
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
      <div className="grid gap-3 md:grid-cols-2">
        {filtered.map((d) => {
          const people = d.authors.length ? d.authors : d.attendees
          return (
            <Link key={d.doc_id} to={`/documents/${d.doc_id}`}>
              <Card className="h-full p-4 transition hover:border-brand-500 hover:shadow-md">
                <div className="flex items-start gap-3">
                  <SourceIcon type={d.source_type} className="mt-0.5 size-5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{d.title}</p>
                    <p className="truncate font-mono text-[11px] text-slate-500">{d.source_file}</p>
                  </div>
                  {d.date && <span className="shrink-0 text-xs text-slate-500">{d.date}</span>}
                </div>
                <div className="mt-2">
                  <MetaBadges type={d.source_type} topic={d.topic_domain} priority={d.priority} products={d.products} />
                </div>
                {d.summary && <p className="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-slate-400">{d.summary}</p>}
                <p className="mt-2 truncate text-xs text-slate-500">
                  <span className="font-medium">{d.authors.length ? 'Author' : 'Attendees'}:</span> {people.join(', ') || 'unknown'}
                </p>
              </Card>
            </Link>
          )
        })}
      </div>
    </>
  )
}
