import { ChevronDown, Download, ExternalLink, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'
import { displayTitle, fileName, peopleLabel } from '../lib/format'
import type { Citation, DocumentContent } from '../types'
import { MetaBadges, SourceIcon } from './meta'
import { Badge, cn, Spinner } from './ui'

type Hover = (n: number | null) => void

/** Inline [n] marker. Hover/focus lights up the matching evidence entry; click opens the passage. */
export function CitationChip({ citation, n, onOpen, active, onHover }: {
  citation?: Citation
  n: number
  onOpen?: (c: Citation) => void
  active?: boolean
  onHover?: Hover
}) {
  if (!citation) return <sup className="text-[10px] text-slate-400">[{n}]</sup>
  const who = citation.people.join(', ') || 'not recorded'
  return (
    <button
      type="button"
      onMouseEnter={() => onHover?.(n)}
      onMouseLeave={() => onHover?.(null)}
      onFocus={() => onHover?.(n)}
      onBlur={() => onHover?.(null)}
      onClick={() => onOpen?.(citation)}
      className={cn(
        'mx-0.5 inline-flex h-[18px] min-w-[18px] translate-y-[-1px] items-center justify-center rounded-[4px] px-1 align-middle font-mono text-[10.5px] font-medium ring-1 transition-colors',
        active
          ? 'cite-active'
          : 'bg-brand-50 text-brand-700 ring-brand-200 hover:bg-brand-100 dark:bg-brand-900/60 dark:text-brand-100 dark:ring-brand-700',
      )}
      aria-label={`Source ${n}: ${fileName(citation.source_file)}, ${peopleLabel(citation.source_type, citation.people.length)} ${who}`}
    >
      {n}
    </button>
  )
}

/**
 * The evidence rail: every cited source with its file, people and date, always visible.
 * Entries are linked to the inline markers through the shared `active` number.
 */
export function EvidenceRail({ citations, cited, active, onHover, onOpen }: {
  citations: Citation[]
  cited: Set<number>
  active: number | null
  onHover: Hover
  onOpen: (c: Citation) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const used = cited.size ? citations.filter((c) => cited.has(c.n)) : citations
  const unused = cited.size ? citations.filter((c) => !cited.has(c.n)) : []
  const docs = new Set(used.map((c) => c.doc_id)).size
  const heading = cited.size ? 'Sources' : 'Closest matches'
  return (
    <aside aria-label={heading}>
      <div className="mb-2">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold">{heading}</h3>
          <span className="text-xs text-slate-500">
            {used.length} passage{used.length === 1 ? '' : 's'} from {docs} file{docs === 1 ? '' : 's'}
          </span>
        </div>
        {!cited.size && <p className="mt-0.5 text-xs text-slate-500">Retrieved, but not enough to answer from.</p>}
      </div>
      <ol className="space-y-1.5">
        {used.map((c) => (
          <EvidenceItem key={c.chunk_id} c={c} active={active === c.n} onHover={onHover} onOpen={onOpen} />
        ))}
      </ol>
      {unused.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowAll((s) => !s)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          >
            <ChevronDown className={cn('size-3.5 transition-transform', showAll && 'rotate-180')} />
            {showAll ? 'Hide' : 'Show'} {unused.length} retrieved but not cited
          </button>
          {showAll && (
            <ol className="mt-1.5 space-y-1.5 opacity-80">
              {unused.map((c) => (
                <EvidenceItem key={c.chunk_id} c={c} active={active === c.n} onHover={onHover} onOpen={onOpen} />
              ))}
            </ol>
          )}
        </div>
      )}
    </aside>
  )
}

function EvidenceItem({ c, active, onHover, onOpen }: {
  c: Citation
  active: boolean
  onHover: Hover
  onOpen: (c: Citation) => void
}) {
  const ref = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [active])
  return (
    <li ref={ref}>
      <button
        type="button"
        onMouseEnter={() => onHover(c.n)}
        onMouseLeave={() => onHover(null)}
        onFocus={() => onHover(c.n)}
        onBlur={() => onHover(null)}
        onClick={() => onOpen(c)}
        className={cn(
          'group w-full rounded-md border px-3 py-2.5 text-left transition-colors',
          active
            ? 'border-brand-200 bg-brand-50 dark:border-brand-700 dark:bg-brand-900/40'
            : 'border-slate-200/90 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-[#121a1d] dark:hover:border-slate-700',
        )}
      >
        <div className="flex items-start gap-2.5">
          <span
            className={cn(
              'mt-px flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-[4px] px-1 font-mono text-[10.5px] font-medium ring-1',
              active ? 'cite-active' : 'bg-brand-50 text-brand-700 ring-brand-200 dark:bg-brand-900/60 dark:text-brand-100 dark:ring-brand-700',
            )}
          >
            {c.n}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="line-clamp-2 text-[13px] leading-snug font-medium">{displayTitle(c.title, fileName(c.source_file))}</p>
            <p className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <SourceIcon type={c.source_type} className="size-3.5 shrink-0" />
              <span className="truncate font-mono text-[11px]">{fileName(c.source_file)}</span>
            </p>
            <p className="text-xs text-slate-700 dark:text-slate-300">
              <span className="text-slate-500 dark:text-slate-400">{peopleLabel(c.source_type, c.people.length)} </span>
              {c.people.length ? c.people.join(', ') : <span className="text-slate-400">not recorded</span>}
            </p>
            <p className="flex flex-wrap gap-x-3 text-[11px] text-slate-500 dark:text-slate-400">
              {c.date && <span className="tabular-nums">{c.date}</span>}
              {c.section && <span className="truncate">{sectionLabel(c.section)}</span>}
            </p>
            {active && (
              <p className="line-clamp-4 border-l-2 border-brand-200 pl-2 text-xs leading-relaxed text-slate-600 dark:border-brand-700 dark:text-slate-300">
                {plainSnippet(c.snippet)}
              </p>
            )}
          </div>
        </div>
      </button>
    </li>
  )
}

/** Full source card (review queue): title, file, people, date, metadata and the passage. */
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
            {displayTitle(c.title, fileName(c.source_file))}
          </p>
          <p className="truncate font-mono text-[11px] text-slate-500 dark:text-slate-400" title={c.source_file}>
            {c.source_file}
          </p>
        </div>
        <Badge tone="brand">{c.n}</Badge>
      </div>
      <p className="text-xs text-slate-700 dark:text-slate-300">
        <span className="text-slate-500">{peopleLabel(c.source_type, c.people.length)} </span>
        {c.people.join(', ') || 'not recorded'}
      </p>
      <p className="flex flex-wrap gap-x-3 text-[11px] text-slate-500">
        {c.date && <span>{c.date}</span>}
        {c.section && <span className="truncate">{sectionLabel(c.section)}</span>}
      </p>
      <MetaBadges topic={c.topic_domain} priority={c.priority} products={c.products} />
      <p
        className={cn(
          'rounded-md bg-slate-50 p-2 text-xs leading-relaxed whitespace-pre-line text-slate-600 dark:bg-slate-800/60 dark:text-slate-300',
          compact ? 'line-clamp-5' : 'line-clamp-[10]',
        )}
      >
        {plainSnippet(c.snippet)}
      </p>
      {onOpen && (
        <button
          onClick={() => onOpen(c)}
          className="flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline dark:text-brand-200"
        >
          Open in document <ExternalLink className="size-3" />
        </button>
      )}
    </div>
  )
}

/** Section path ("A > B") with all-caps banners in title case. */
const sectionLabel = (path: string) =>
  path
    .split(' > ')
    .map((p) => displayTitle(p))
    .join(' › ')

const plainSnippet = (s: string) =>
  s
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*|__|`/g, '')
    .replace(/^\s*[-*+]\s+/gm, '• ')
    .replace(/\n{2,}/g, '\n')
    .trim()

const CITE = /\[(\d+)\]/g

/** Markdown answer with [n] markers rendered as citation markers linked to the evidence rail. */
export function AnswerMarkdown({ text, citations, onOpen, streaming, active, onHover }: {
  text: string
  citations: Citation[]
  onOpen?: (c: Citation) => void
  streaming?: boolean
  active?: number | null
  onHover?: Hover
}) {
  const byN = new Map(citations.map((c) => [c.n, c]))
  const md = text.replace(CITE, (_, n) => `[${n}](#cite-${n})`)
  return (
    <div
      className={cn(
        'prose max-w-none text-[15px] leading-7 prose-slate dark:prose-invert prose-p:my-2 prose-ul:my-2 prose-li:my-1 prose-headings:mt-4 prose-headings:mb-1.5 prose-headings:text-base prose-strong:font-semibold',
        streaming && 'streaming-caret',
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const m = href?.match(/^#cite-(\d+)$/)
            if (m) {
              const n = Number(m[1])
              return <CitationChip n={n} citation={byN.get(n)} onOpen={onOpen} active={active === n} onHover={onHover} />
            }
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

/** Slide-over document viewer that highlights the cited passage. */
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
      <div className="absolute inset-0 bg-slate-950/25" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-[#121a1d]">
        <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <span className="text-sm font-medium text-slate-600 dark:text-slate-300">Source document</span>
          <div className="flex items-center gap-1">
            <Link
              to={`/documents/${docId}${chunkId ? `?chunk=${encodeURIComponent(chunkId)}` : ''}`}
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Open full page"
            >
              <ExternalLink className="size-4" />
            </Link>
            <button
              onClick={onClose}
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Close"
            >
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

const SectionHeading = ({ children }: { children: React.ReactNode }) => (
  <h3 className="mb-1.5 text-sm font-semibold text-slate-700 dark:text-slate-200">{children}</h3>
)

export function DocumentBody({ data, chunkId }: { data: DocumentContent; chunkId?: string | null }) {
  const d = data.document
  const target = useRef<HTMLDivElement>(null)
  useEffect(() => {
    target.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [chunkId, data])
  const roles = { ...d.attendee_roles, ...d.author_roles }
  const people = d.source_type === 'meeting' ? d.attendees : d.authors
  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex items-start gap-3">
          <SourceIcon type={d.source_type} className="mt-1 size-5 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-xl leading-snug font-semibold">{displayTitle(d.title, fileName(d.source_file))}</h2>
            <p className="font-mono text-xs text-slate-500">{d.source_file}</p>
          </div>
        </div>
        <MetaBadges type={d.source_type} topic={d.topic_domain} priority={d.priority} products={d.products} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-slate-500">{peopleLabel(d.source_type, people.length)}</dt>
          <dd>
            {people.length
              ? people.map((p, i) => (
                  <span key={p}>
                    {i > 0 && ', '}
                    <span className="font-medium">{p}</span>
                    {roles[p] && <span className="text-slate-500"> ({roles[p]})</span>}
                  </span>
                ))
              : <span className="text-slate-400">not recorded</span>}
          </dd>
          {d.reviewers.length > 0 && (
            <>
              <dt className="text-slate-500">Reviewed by</dt>
              <dd>{d.reviewers.join(', ')}</dd>
            </>
          )}
          <dt className="text-slate-500">Date</dt>
          <dd className="tabular-nums">{d.date ?? <span className="text-slate-400">undated</span>}</dd>
          {d.meeting_type && (
            <>
              <dt className="text-slate-500">Type</dt>
              <dd>{d.meeting_type}</dd>
            </>
          )}
        </dl>
        <a
          href={api.documentFileUrl(d.doc_id)}
          className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline dark:text-brand-200"
        >
          <Download className="size-3.5" /> Download original
        </a>
      </header>

      {d.summary && (
        <section className="rounded-md border-l-2 border-brand-200 bg-brand-50/50 px-3 py-2.5 text-sm leading-relaxed dark:border-brand-700 dark:bg-brand-900/20">
          <SectionHeading>Summary</SectionHeading>
          <p>{d.summary}</p>
        </section>
      )}

      {(d.decisions.length > 0 || d.action_items.length > 0) && (
        <section className="grid gap-4 sm:grid-cols-2">
          {d.decisions.length > 0 && (
            <div>
              <SectionHeading>Decisions</SectionHeading>
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {d.decisions.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          {d.action_items.length > 0 && (
            <div>
              <SectionHeading>Action items</SectionHeading>
              <ul className="space-y-1 text-sm">
                {d.action_items.map((a) => (
                  <li key={a.task}>
                    <span className="font-medium">{a.owner}</span>: {a.task}
                    {a.due_date && <span className="text-slate-500"> (due {a.due_date})</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section>
        <SectionHeading>
          Content <span className="font-normal text-slate-500">({data.chunks.length} passages)</span>
        </SectionHeading>
        <div className="space-y-2">
          {data.chunks.map((c) => {
            const hit = c.chunk_id === chunkId
            return (
              <div
                key={c.chunk_id}
                ref={hit ? target : undefined}
                id={c.chunk_id}
                className={cn(
                  'rounded-md border p-3 text-sm',
                  hit ? 'chunk-highlight border-amber-300 dark:border-amber-600' : 'border-slate-200/80 dark:border-slate-800',
                )}
              >
                <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-slate-500">
                  <span className="truncate">{c.section ? sectionLabel(c.section) : `Passage ${c.chunk_index + 1}`}</span>
                  {hit && <Badge tone="amber">Cited passage</Badge>}
                </div>
                <div className="prose prose-sm max-w-none overflow-x-auto prose-slate dark:prose-invert prose-p:my-1 prose-headings:my-1.5 prose-headings:text-sm prose-table:text-xs">
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
