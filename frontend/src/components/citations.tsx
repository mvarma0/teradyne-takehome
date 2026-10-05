import { Download, ExternalLink, Users, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'
import { fileName, humanize } from '../lib/format'
import type { Citation, DocumentContent } from '../types'
import { MetaBadges, SourceIcon } from './meta'
import { Badge, cn, Spinner } from './ui'

/** Inline [n] chip. Hover shows the source card; click opens the document at the chunk. */
export function CitationChip({ citation, n, onOpen }: {
  citation?: Citation
  n: number
  onOpen?: (c: Citation) => void
}) {
  const ref = useRef<HTMLButtonElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number; above: boolean } | null>(null)
  const timer = useRef<number | undefined>(undefined)

  if (!citation) {
    return <sup className="text-[10px] text-slate-400">[{n}]</sup>
  }
  const show = () => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      const r = ref.current?.getBoundingClientRect()
      if (r) setPos({ x: r.left + r.width / 2, y: r.top < 260 ? r.bottom : r.top, above: r.top >= 260 })
    }, 120)
  }
  const hide = () => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setPos(null), 150)
  }
  return (
    <>
      <button
        ref={ref}
        type="button"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={() => onOpen?.(citation)}
        className="mx-0.5 inline-flex h-[18px] min-w-[18px] translate-y-[-1px] items-center justify-center rounded-md bg-brand-50 px-1 align-middle text-[10px] font-semibold text-brand-700 ring-1 ring-brand-100 transition hover:bg-brand-600 hover:text-white dark:bg-brand-700/30 dark:text-brand-100 dark:ring-brand-700/50"
        aria-label={`Source ${n}: ${fileName(citation.source_file)}`}
      >
        {n}
      </button>
      {pos &&
        createPortal(
          <div
            onMouseEnter={() => window.clearTimeout(timer.current)}
            onMouseLeave={hide}
            style={{
              left: Math.min(Math.max(pos.x, 180), window.innerWidth - 180),
              top: pos.y,
              transform: `translate(-50%, ${pos.above ? 'calc(-100% - 8px)' : '8px'})`,
            }}
            className="fixed z-[60] w-[340px] rounded-xl border border-slate-200 bg-white p-3 text-left shadow-xl dark:border-slate-700 dark:bg-slate-900"
          >
            <SourceCard citation={citation} onOpen={onOpen} compact />
          </div>,
          document.body,
        )}
    </>
  )
}

export function SourceCard({ citation: c, onOpen, compact }: {
  citation: Citation
  onOpen?: (c: Citation) => void
  compact?: boolean
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2">
        <SourceIcon type={c.source_type} className="mt-0.5 size-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={c.title ?? ''}>
            {c.title ?? fileName(c.source_file)}
          </p>
          <p className="truncate font-mono text-[11px] text-slate-500 dark:text-slate-400" title={c.source_file}>
            {c.source_file}
          </p>
        </div>
        <Badge tone="brand">[{c.n}]</Badge>
      </div>
      <div className="flex items-start gap-1.5 text-xs text-slate-600 dark:text-slate-300">
        <Users className="mt-0.5 size-3.5 shrink-0 text-slate-400" />
        <span>
          <span className="font-medium">{c.people_label}:</span> {c.people.join(', ') || 'unknown'}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[11px] text-slate-500">
        {c.date && <span>{c.date}</span>}
        {c.section && <span className="truncate">· {c.section}</span>}
      </div>
      <MetaBadges topic={c.topic_domain} priority={c.priority} products={c.products} />
      <p
        className={cn(
          'rounded-lg bg-slate-50 p-2 text-xs leading-relaxed whitespace-pre-line text-slate-600 dark:bg-slate-800/60 dark:text-slate-300',
          compact ? 'line-clamp-5' : 'line-clamp-[10]',
        )}
      >
        {plainSnippet(c.snippet)}
      </p>
      {onOpen && (
        <button
          onClick={() => onOpen(c)}
          className="flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline dark:text-brand-100"
        >
          Open in document <ExternalLink className="size-3" />
        </button>
      )}
    </div>
  )
}

const plainSnippet = (s: string) =>
  s
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*|__|`/g, '')
    .replace(/^\s*[-*+]\s+/gm, '• ')
    .replace(/\n{2,}/g, '\n')
    .trim()

const CITE = /\[(\d+)\]/g

/** Markdown answer with [n] markers rendered as citation chips. */
export function AnswerMarkdown({ text, citations, onOpen, streaming }: {
  text: string
  citations: Citation[]
  onOpen?: (c: Citation) => void
  streaming?: boolean
}) {
  const byN = new Map(citations.map((c) => [c.n, c]))
  const md = text.replace(CITE, (_, n) => `[${n}](#cite-${n})`)
  return (
    <div
      className={cn(
        'prose prose-sm max-w-none prose-slate dark:prose-invert prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5 prose-headings:mt-3 prose-headings:mb-1.5',
        streaming && 'streaming-caret',
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const m = href?.match(/^#cite-(\d+)$/)
            if (m) return <CitationChip n={Number(m[1])} citation={byN.get(Number(m[1]))} onOpen={onOpen} />
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            )
          },
        }}
      >
        {md || (streaming ? '​' : '')}
      </ReactMarkdown>
    </div>
  )
}

/** Slide-over document viewer that highlights the cited chunk. */
export function DocumentDrawer({ docId, chunkId, onClose }: {
  docId: string | null
  chunkId?: string | null
  onClose: () => void
}) {
  const [data, setData] = useState<DocumentContent | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!docId) return
    setData(null)
    setError(null)
    api.documentContent(docId).then(setData).catch((e) => setError(String(e.message ?? e)))
  }, [docId])
  useEffect(() => {
    if (!docId) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [docId, onClose])

  if (!docId) return null
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-950/20 backdrop-blur-[1px]" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <span className="text-xs font-medium tracking-wide text-slate-500 uppercase">Source document</span>
          <div className="flex items-center gap-1">
            <Link
              to={`/documents/${docId}${chunkId ? `?chunk=${encodeURIComponent(chunkId)}` : ''}`}
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Open full page"
            >
              <ExternalLink className="size-4" />
            </Link>
            <button onClick={onClose} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
              <X className="size-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && <p className="text-sm text-rose-600">{error}</p>}
          {!data && !error && <Spinner />}
          {data && <DocumentBody data={data} chunkId={chunkId} />}
        </div>
      </aside>
    </div>
  )
}

export function DocumentBody({ data, chunkId }: { data: DocumentContent; chunkId?: string | null }) {
  const d = data.document
  const target = useRef<HTMLDivElement>(null)
  useEffect(() => {
    target.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [chunkId, data])
  const roles = { ...d.attendee_roles, ...d.author_roles }
  const people = d.authors.length ? d.authors : d.attendees
  return (
    <div className="space-y-5">
      <header className="space-y-3">
        <div className="flex items-start gap-3">
          <SourceIcon type={d.source_type} className="mt-1 size-5 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-lg leading-snug font-semibold">{d.title}</h2>
            <p className="font-mono text-xs text-slate-500">{d.source_file}</p>
          </div>
        </div>
        <MetaBadges type={d.source_type} topic={d.topic_domain} priority={d.priority} products={d.products} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-slate-500">{d.authors.length ? 'Author' : 'Attendees'}</dt>
          <dd>
            {people.length
              ? people.map((p, i) => (
                  <span key={p}>
                    {i > 0 && ', '}
                    <span className="font-medium">{p}</span>
                    {roles[p] && <span className="text-slate-500"> ({roles[p]})</span>}
                  </span>
                ))
              : 'unknown'}
          </dd>
          {d.reviewers.length > 0 && (
            <>
              <dt className="text-slate-500">Reviewed by</dt>
              <dd>{d.reviewers.join(', ')}</dd>
            </>
          )}
          {d.date && (
            <>
              <dt className="text-slate-500">Date</dt>
              <dd>{d.date}</dd>
            </>
          )}
          {d.meeting_type && (
            <>
              <dt className="text-slate-500">Type</dt>
              <dd>{d.meeting_type}</dd>
            </>
          )}
        </dl>
        <div className="flex gap-2">
          <a
            href={api.documentFileUrl(d.doc_id)}
            className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline dark:text-brand-100"
          >
            <Download className="size-3.5" /> Download original
          </a>
        </div>
      </header>

      {d.summary && (
        <section className="rounded-xl bg-slate-50 p-3 text-sm dark:bg-slate-800/50">
          <h3 className="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">Summary</h3>
          <p>{d.summary}</p>
        </section>
      )}

      {(d.decisions.length > 0 || d.action_items.length > 0) && (
        <section className="grid gap-3 sm:grid-cols-2">
          {d.decisions.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">Decisions</h3>
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {d.decisions.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          {d.action_items.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">Action items</h3>
              <ul className="space-y-1 text-sm">
                {d.action_items.map((a) => (
                  <li key={a.task}>
                    <span className="font-medium">{a.owner}</span>: {a.task}
                    {a.due_date && <span className="text-slate-500"> · due {a.due_date}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
          Content · {data.chunks.length} chunks
        </h3>
        <div className="space-y-2">
          {data.chunks.map((c) => {
            const hit = c.chunk_id === chunkId
            return (
              <div
                key={c.chunk_id}
                ref={hit ? target : undefined}
                id={c.chunk_id}
                className={cn(
                  'rounded-lg border p-3 text-sm',
                  hit
                    ? 'chunk-highlight border-amber-300 dark:border-amber-600'
                    : 'border-slate-100 dark:border-slate-800',
                )}
              >
                <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-slate-400">
                  <span className="truncate">{c.section ? humanize(c.section) : `Chunk ${c.chunk_index + 1}`}</span>
                  {hit && <Badge tone="amber">Cited</Badge>}
                </div>
                <div className="prose prose-sm max-w-none prose-slate dark:prose-invert prose-p:my-1 prose-table:text-xs">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{c.text}</ReactMarkdown>
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
