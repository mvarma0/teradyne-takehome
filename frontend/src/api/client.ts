import type {
  AnswerPayload,
  Citation,
  Conversation,
  DocumentContent,
  DocumentMeta,
  EvalRun,
  Gap,
  Guardrails,
  MetricsSummary,
  QueryFilters,
  Routing,
  Stats,
  StoredMessage,
} from '../types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
const qs = (params: Record<string, string | undefined>) => {
  const p = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  stats: () => request<Stats>('/stats'),
  ingest: (force = false) => request<Record<string, unknown>>('/ingest', json({ force })),

  documents: (filters: Record<string, string | undefined> = {}) =>
    request<DocumentMeta[]>(`/documents${qs(filters)}`),
  documentContent: (id: string) => request<DocumentContent>(`/documents/${id}/content`),
  documentFileUrl: (id: string) => `/api/documents/${id}/file`,

  conversations: () => request<Conversation[]>('/conversations'),
  conversation: (id: string) =>
    request<Conversation & { messages: StoredMessage[] }>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),

  feedback: (queryId: string, rating: 'up' | 'down' | null) =>
    request(`/query/${queryId}/feedback`, json({ rating })),
  correct: (queryId: string, correction: string, submittedBy?: string) =>
    request<Gap>(`/query/${queryId}/correct`, json({ correction, submitted_by: submittedBy })),
  reject: (queryId: string, reason: string, submittedBy?: string) =>
    request<Gap>(`/query/${queryId}/reject`, json({ reason, submitted_by: submittedBy })),
  sendRouting: (routingId: string, question: string, sentBy?: string) =>
    request<Routing>(`/routing/${routingId}/send`, json({ question, sent_by: sentBy })),
  dismissRouting: (routingId: string) => request<Routing>(`/routing/${routingId}/dismiss`, json({})),

  reviewQueue: (filters: { status?: string; type?: string } = {}) =>
    request<{ counts: { pending: number; total: number; by_type: Record<string, number> }; items: Gap[] }>(
      `/review-queue${qs(filters)}`,
    ),
  review: (gapId: string, review_status: string, reviewer_note?: string) =>
    request<Gap>(`/review-queue/${gapId}`, {
      method: 'PATCH',
      body: JSON.stringify({ review_status, reviewer_note }),
    }),

  metrics: (window: string) => request<MetricsSummary>(`/metrics?window=${window}`),

  evals: () => request<{ datasets: Record<string, number | string>; runs: EvalRun[] }>('/evals'),
  evalRun: (id: string) => request<EvalRun>(`/evals/${id}`),
  startEval: (dataset: string) => request<{ run_id: string }>('/evals/run', json({ dataset })),
  synthesize: (n: number) => request<{ generated: number }>('/evals/synthesize', json({ n })),
}

// ---- Server-Sent Events chat stream ------------------------------------------------------
export type StreamEvent =
  | { event: 'conversation'; data: { conversation_id: string; title: string } }
  | { event: 'status'; data: { stage: string; query?: string } }
  | { event: 'guardrail'; data: Pick<Guardrails, 'category' | 'reason' | 'method'> }
  | { event: 'sources'; data: { citations: Citation[]; documents: DocumentMeta[] } }
  | { event: 'token'; data: { text: string } }
  | { event: 'final'; data: AnswerPayload }
  | { event: 'error'; data: { detail: string } }

export async function streamChat(
  body: { message: string; conversation_id?: string | null; filters?: QueryFilters | null },
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      let name = 'message'
      const data: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event: ')) name = line.slice(7)
        else if (line.startsWith('data: ')) data.push(line.slice(6))
      }
      if (data.length) onEvent({ event: name, data: JSON.parse(data.join('\n')) } as StreamEvent)
    }
  }
}
