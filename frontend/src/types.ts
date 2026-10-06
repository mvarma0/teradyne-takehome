export type SourceType = 'meeting' | 'docx' | 'pptx' | 'xlsx'

export interface ActionItem {
  owner: string
  task: string
  due_date: string | null
}

export interface DocumentMeta {
  doc_id: string
  source_file: string
  source_type: SourceType
  title: string | null
  date: string | null
  attendees: string[]
  attendee_roles: Record<string, string>
  authors: string[]
  author_roles: Record<string, string>
  reviewers: string[]
  meeting_type: string | null
  location: string | null
  topic_domain: string | null
  priority: string | null
  products: string[]
  key_topics: string[]
  summary: string | null
  decisions: string[]
  action_items: ActionItem[]
  rules_applied: string[]
  format: string | null
  pages: number | null
  n_chunks: number
  ingested_at: string
}

export interface Citation {
  n: number
  chunk_id: string
  doc_id: string
  source_file: string
  source_type: SourceType
  title: string | null
  section: string | null
  date: string | null
  attendees: string[]
  authors: string[]
  people: string[]
  people_label: string
  topic_domain: string | null
  priority: string | null
  products: string[]
  snippet: string
  scores: { semantic: number | null; bm25: number | null; fused: number; rerank: number | null }
}

export interface Claim {
  text: string
  citations: number[]
  kind: 'fact' | 'meta' | 'structure'
  supported: boolean
}

export interface MatchedSource {
  source_file: string
  title: string | null
  date: string | null
  relation: string
  snippet: string
}

export interface Routing {
  routing_id?: string
  id?: string
  person: string
  role: string | null
  reason: string
  matched_sources: MatchedSource[]
  draft_question: string
  edited_question?: string | null
  status?: 'suggested' | 'sent' | 'dismissed'
  sent_at?: string | null
  sent_by?: string | null
}

export interface Guardrails {
  category: 'knowledge_question' | 'small_talk' | 'off_topic' | 'prompt_injection'
  reason: string
  method: string
  pii_redactions: number
  uncited_dropped: number
}

export type AnswerStatus = 'answered' | 'routed' | 'refused' | 'blocked' | 'rejected' | 'corrected'

export interface AnswerPayload {
  message_id: string
  query_id: string
  conversation_id: string | null
  query: string
  standalone_query: string
  filters: QueryFilters | null
  answer: string
  claims: Claim[]
  dropped_claims: string[]
  citations: Citation[]
  cited?: number[]
  documents: DocumentMeta[]
  confidence: number | null
  confidence_detail?: { components: Record<string, number>; caps: string[] }
  confident: boolean | null
  status: AnswerStatus
  routing: Routing[]
  guardrails: Guardrails
  retrieval: {
    semantic_candidates: number
    bm25_candidates: number
    fused_candidates: number
    reranker: string
  } | null
  latency_ms: number
  first_token_ms: number | null
  feedback?: 'up' | 'down' | null
}

export interface QueryFilters {
  topic_domain?: string
  priority?: string
  source_type?: string
  person?: string
  date_from?: string
  date_to?: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  n_messages?: number
}

export interface StoredMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  status: AnswerStatus | null
  feedback: 'up' | 'down' | null
  payload: AnswerPayload | null
  created_at: string
}

export interface Gap {
  id: string
  message_id: string | null
  conversation_id: string | null
  type: 'low_confidence' | 'rejected' | 'correction'
  query_text: string
  original_answer: string | null
  correction_text: string | null
  reason: string | null
  submitted_by: string | null
  review_status: 'pending' | 'reviewed' | 'resolved'
  reviewer_note: string | null
  created_at: string
  reviewed_at: string | null
  confidence: number | null
  routing: Routing[]
  citations: Citation[]
}

export interface MetricsRollup {
  queries: number
  knowledge_queries: number
  answer_rate: number | null
  routed_rate: number | null
  guardrail_blocks: number
  guardrail_by_type: Record<string, number>
  mean_confidence: number | null
  mean_top_semantic: number | null
  mean_top_rerank: number | null
  citation_valid_ratio: number | null
  uncited_dropped: number
  pii_redactions: number
  p50_latency_ms: number | null
  p95_latency_ms: number | null
  p50_first_token_ms: number | null
  feedback_up: number
  feedback_down: number
  negative_feedback_rate: number | null
  rejections: number
  corrections: number
  low_confidence_gaps: number
}

export interface Alert {
  metric: string
  value: number
  threshold: number
  severity: 'warning' | 'critical'
  message: string
}

export interface MetricsSummary {
  window: string
  from: string
  to: string
  current: MetricsRollup
  baseline: MetricsRollup
  alerts: Alert[]
  timeseries: {
    bucket: string
    queries: number
    answer_rate: number | null
    mean_confidence: number | null
    p95_latency_ms: number | null
    guardrail_blocks: number
  }[]
}

export interface EvalSummary {
  cases: number
  hit_rate: number | null
  mrr: number | null
  cited_expected_rate: number | null
  answerability_accuracy: number | null
  unanswerable_refusal_rate: number | null
  keyword_recall: number | null
  faithfulness: number | null
  relevance: number | null
  citation_valid_ratio: number | null
  mean_confidence: number | null
  p50_latency_ms: number | null
}

export interface EvalRun {
  id: string
  dataset: string
  status: 'running' | 'completed' | 'failed'
  started_at: string
  finished_at: string | null
  config: Record<string, string | number> | null
  summary: EvalSummary | null
  error: string | null
  done?: number
  total?: number
  results?: EvalResult[]
}

export interface EvalResult {
  case_id: string
  question: string
  answer: string
  expected: { expected_sources?: string[]; expected_keywords?: string[]; answerable?: boolean }
  answerable: boolean
  confident: boolean | null
  confidence: number | null
  status: string
  hit: boolean | null
  reciprocal_rank: number | null
  cited_expected: boolean | null
  answerability_correct: boolean
  keyword_recall: number | null
  faithfulness?: number | null
  relevance?: number | null
  judge_reason?: string
  citation_valid_ratio: number | null
  latency_ms: number
  retrieved: string[]
}

export interface Stats {
  documents: number
  by_type: Record<string, number>
  chunks: number
  collection: string
  llm: string
  embeddings: string
  reranker: string
  confidence_threshold: number
}

export interface DocumentContent {
  document: DocumentMeta
  content: string | null
  chunks: { chunk_id: string; chunk_index: number; section: string | null; text: string }[]
}

export interface TraceSummary {
  id: string
  conversation_id: string | null
  query_text: string
  standalone_query: string | null
  status: AnswerStatus
  confidence: number | null
  feedback: 'up' | 'down' | null
  created_at: string
  n_gaps: number
  n_retrieved: number
  n_cited: number
  cited_files: string[]
  guardrail: Guardrails['category'] | null
  latency_ms: number | null
}

export type TraceGap = Omit<Gap, 'conversation_id' | 'confidence' | 'routing' | 'citations'>

export interface Trace extends Omit<AnswerPayload, 'routing'> {
  id: string
  created_at: string
  routing: Routing[]
  gaps: TraceGap[]
}

export interface UploadResult {
  source_file: string
  replaced: boolean
  report: Record<string, unknown>
}
