import { ArrowLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { DocumentBody } from '../components/citations'
import { Badge, Card, ErrorBanner, Spinner } from '../components/ui'
import type { DocumentContent } from '../types'

export default function DocumentViewerPage() {
  const { docId } = useParams()
  const [params] = useSearchParams()
  const [data, setData] = useState<DocumentContent | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (docId) api.documentContent(docId).then(setData).catch((e) => setError(e.message))
  }, [docId])
  return (
    <>
      <Link to="/documents" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">
        <ArrowLeft className="size-4" /> All documents
      </Link>
      <ErrorBanner error={error} />
      {!data && !error && <Spinner />}
      {data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
          <Card className="p-6">
            <DocumentBody data={data} chunkId={params.get('chunk')} />
          </Card>
          <aside className="space-y-3 text-sm">
            <Card className="p-4">
              <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">Provenance</h3>
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between gap-2"><dt className="text-slate-500">Format</dt><dd>{data.document.format ?? 'markdown'}</dd></div>
                {data.document.pages && <div className="flex justify-between gap-2"><dt className="text-slate-500">Pages / slides / sheets</dt><dd>{data.document.pages}</dd></div>}
                <div className="flex justify-between gap-2"><dt className="text-slate-500">Chunks</dt><dd>{data.document.n_chunks}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-slate-500">Ingested</dt><dd>{new Date(data.document.ingested_at).toLocaleString()}</dd></div>
              </dl>
            </Card>
            {data.document.key_topics.length > 0 && (
              <Card className="p-4">
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">Key topics</h3>
                <div className="flex flex-wrap gap-1">{data.document.key_topics.map((t) => <Badge key={t}>{t}</Badge>)}</div>
              </Card>
            )}
            {data.document.rules_applied.length > 0 && (
              <Card className="p-4">
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">Business rules applied</h3>
                <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
                  {data.document.rules_applied.map((r) => <li key={r}>{r}</li>)}
                </ul>
              </Card>
            )}
          </aside>
        </div>
      )}
    </>
  )
}
