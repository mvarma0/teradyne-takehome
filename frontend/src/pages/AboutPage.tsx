import { Activity, ClipboardCheck, FileStack, FlaskConical, GitBranch, MessagesSquare } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Card, PageHeader } from '../components/ui'
import type { Stats } from '../types'

const FLOW: [string, string][] = [
  ['Ingest', 'Meeting transcripts and Office files (Word, PowerPoint, Excel) are parsed. Attendees and authors come straight from the source; an LLM adds topic, priority, products, summary, decisions and action items.'],
  ['Index', 'Each source is split along its own structure (sections, slides, sheets) and stored twice: as vectors for meaning and as keywords for exact terms.'],
  ['Retrieve', 'A question is checked by guardrails, rewritten if it is a follow-up, then matched by meaning and by keyword. The results are fused and reranked by relevance.'],
  ['Answer', 'The answer is written only from the retrieved passages. Every statement must cite one; statements without a valid citation are removed.'],
  ['Route', 'If confidence is low, the system names the people most likely to know (the authors and attendees of the closest sources) and drafts the question to send them.'],
  ['Improve', 'Corrections, rejections and low-confidence answers go to a review queue. Monitoring and evals track whether quality is slipping.'],
]

const PAGES: { to: string; icon: ReactNode; title: string; text: string }[] = [
  { to: '/chat', icon: <MessagesSquare className="size-4" />, title: 'Ask', text: 'Ask in plain language. Hover a citation number to see its source; click it to open the passage. Rate, correct or reject any answer.' },
  { to: '/documents', icon: <FileStack className="size-4" />, title: 'Documents', text: 'Every indexed source with its derived metadata. Upload a new or updated file, or re-ingest the data folder.' },
  { to: '/trace', icon: <GitBranch className="size-4" />, title: 'Traceability', text: 'Follow any answer from the question through retrieval, citations and confidence to where it ended up.' },
  { to: '/review', icon: <ClipboardCheck className="size-4" />, title: 'Review queue', text: 'For team leads: low-confidence answers, rejections and corrections, with the original question, answer and suggested people.' },
  { to: '/monitoring', icon: <Activity className="size-4" />, title: 'Monitoring', text: 'Answer rate, confidence, citation validity, feedback and latency against the previous period, with alerts.' },
  { to: '/evals', icon: <FlaskConical className="size-4" />, title: 'Evals', text: 'Run golden and synthetic question sets to measure retrieval and answer quality over time.' },
]

const PROMISES = [
  'Every fact names its source file and the people behind it (attendees for meetings, authors for documents).',
  'People are never invented: names come only from the source files, never from the model.',
  'If the sources do not settle a question, it says so and suggests who to ask instead of guessing.',
  'Prompt-injection attempts are blocked and personal data such as emails and phone numbers is redacted.',
]

export default function AboutPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])
  return (
    <div className="max-w-3xl">
      <PageHeader
        title="About this system"
        subtitle="FastChip's knowledge base: ask questions about meetings and documents and get answers you can check."
      />

      <section className="space-y-3 text-[15px] leading-relaxed text-slate-700 dark:text-slate-300">
        <p>
          Engineering, operations and product knowledge at FastChip is spread across meeting notes, reports, slide decks and
          trackers. Finding out what was decided, who owns an action or why yield dropped means knowing which file to open and
          who to ask.
        </p>
        <p>
          This system reads those sources and answers questions in plain language. Each answer shows exactly where it came from,
          so you can trust it or check it. When the sources are not enough, it tells you who is likely to know.
        </p>
      </section>

      <h2 className="mt-10 mb-3 text-lg font-semibold tracking-tight">How it works</h2>
      <ol className="space-y-3">
        {FLOW.map(([title, text], i) => (
          <li key={title} className="flex gap-3">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
              {i + 1}
            </span>
            <p className="text-sm leading-relaxed">
              <span className="font-semibold">{title}.</span> <span className="text-slate-600 dark:text-slate-400">{text}</span>
            </p>
          </li>
        ))}
      </ol>

      <h2 className="mt-10 mb-3 text-lg font-semibold tracking-tight">What you can rely on</h2>
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-600 dark:text-slate-400">
        {PROMISES.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>

      <h2 className="mt-10 mb-3 text-lg font-semibold tracking-tight">Pages</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {PAGES.map((p) => (
          <Link key={p.to} to={p.to}>
            <Card className="h-full p-4 transition-colors hover:border-brand-500/60">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <span className="text-brand-600 dark:text-brand-200">{p.icon}</span> {p.title}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{p.text}</p>
            </Card>
          </Link>
        ))}
      </div>

      {stats && (
        <p className="mt-10 border-t border-slate-200/80 pt-4 text-xs text-slate-500 dark:border-slate-800">
          Currently indexed: {stats.documents} sources ({stats.chunks} passages). Answer model {stats.llm}; search embeddings{' '}
          {stats.embeddings}; reranker {stats.reranker}; confidence threshold {stats.confidence_threshold}.
        </p>
      )}
    </div>
  )
}
