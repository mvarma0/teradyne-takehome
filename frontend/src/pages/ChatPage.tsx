import { CornerDownLeft } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, streamChat } from '../api/client'
import { AssistantMessage, Composer, SUGGESTIONS, UserBubble, type UiMessage } from '../components/chat'
import { DocumentDrawer } from '../components/citations'
import { cn, Spinner } from '../components/ui'
import { useConversations } from '../lib/conversationsContext'
import type { AnswerPayload, Citation, QueryFilters, StoredMessage } from '../types'

let keySeq = 0
const nextKey = () => `m${++keySeq}`

function fromStored(m: StoredMessage): UiMessage {
  if (m.role === 'user') return { key: m.id, role: 'user', content: m.content }
  const payload = m.payload ? { ...m.payload, status: m.status ?? m.payload.status, feedback: m.feedback } : undefined
  return { key: m.id, role: 'assistant', content: m.content, payload }
}

export default function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const { refresh: refreshConversations } = useConversations()
  const [counts, setCounts] = useState<Record<string, number> | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [threshold, setThreshold] = useState(0.55)
  const [drawer, setDrawer] = useState<{ docId: string; chunkId: string } | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const createdHere = useRef<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api
      .stats()
      .then((s) => {
        setThreshold(s.confidence_threshold)
        setCounts(s.by_type)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!conversationId) {
      if (!streaming) setMessages([])
      return
    }
    if (createdHere.current === conversationId) {
      createdHere.current = null // just created by our own stream; reload on the next visit
      return
    }
    setLoading(true)
    api
      .conversation(conversationId)
      .then((c) => setMessages(c.messages.map(fromStored)))
      .catch(() => navigate('/chat'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: streaming ? 'auto' : 'smooth', block: 'end' })
  }, [messages, streaming])

  const patchAssistant = (key: string, fn: (m: UiMessage) => UiMessage) =>
    setMessages((ms) => ms.map((m) => (m.key === key ? fn(m) : m)))

  const send = async (text: string, filters: QueryFilters | null) => {
    const aKey = nextKey()
    setMessages((ms) => [
      ...ms,
      { key: nextKey(), role: 'user', content: text },
      { key: aKey, role: 'assistant', content: '', streaming: true, stage: 'guardrails' },
    ])
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat(
        { message: text, conversation_id: conversationId ?? null, filters },
        (e) => {
          switch (e.event) {
            case 'conversation':
              if (e.data.conversation_id !== conversationId) {
                createdHere.current = e.data.conversation_id
                navigate(`/chat/${e.data.conversation_id}`, { replace: !conversationId })
              }
              break
            case 'status':
              patchAssistant(aKey, (m) => ({ ...m, stage: e.data.stage, standalone: e.data.query ?? m.standalone }))
              break
            case 'guardrail':
              patchAssistant(aKey, (m) => ({ ...m, guard: e.data }))
              break
            case 'sources':
              patchAssistant(aKey, (m) => ({ ...m, citations: e.data.citations, documents: e.data.documents }))
              break
            case 'token':
              patchAssistant(aKey, (m) => ({ ...m, content: m.content + e.data.text }))
              break
            case 'final':
              patchAssistant(aKey, (m) => ({ ...m, streaming: false, payload: e.data }))
              break
            case 'error':
              patchAssistant(aKey, (m) => ({ ...m, streaming: false, error: e.data.detail }))
              break
          }
        },
        controller.signal,
      )
    } catch (err) {
      const aborted = (err as Error).name === 'AbortError'
      patchAssistant(aKey, (m) => ({
        ...m,
        streaming: false,
        error: aborted ? undefined : `Request failed: ${(err as Error).message}`,
        content: aborted ? `${m.content}\n\n_(stopped)_` : m.content,
      }))
    } finally {
      setStreaming(false)
      abortRef.current = null
      refreshConversations()
    }
  }

  const openCitation = useCallback((c: Citation) => setDrawer({ docId: c.doc_id, chunkId: c.chunk_id }), [])

  const empty = !loading && messages.length === 0
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className={cn('mx-auto px-6 lg:px-10', empty ? 'max-w-2xl' : 'max-w-[1180px] py-10')}>
          {loading && (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          )}
          {empty && <Welcome counts={counts} onPick={(t) => send(t, null)} />}
          <div className="space-y-8">
            {messages.map((m) =>
              m.role === 'user' ? (
                <UserBubble key={m.key} text={m.content} />
              ) : (
                <AssistantMessage
                  key={m.key}
                  msg={m}
                  threshold={threshold}
                  onOpenCitation={openCitation}
                  onPatch={(patch: Partial<AnswerPayload>) =>
                    patchAssistant(m.key, (x) => (x.payload ? { ...x, payload: { ...x.payload, ...patch } } : x))
                  }
                />
              ),
            )}
          </div>
          <div ref={bottomRef} className="h-4" />
        </div>
      </div>
      <div className={cn('mx-auto w-full px-6 pb-5 lg:px-10', empty ? 'max-w-2xl' : 'max-w-[1180px] lg:pr-[calc(320px+3rem+2.5rem)]')}>
        <Composer onSend={send} disabled={streaming} onStop={() => abortRef.current?.abort()} />
        <p className="mt-2 text-center text-[11px] text-slate-500">
          Every statement cites its source. Point at a number to see the source; click it to open the passage.
        </p>
      </div>
      <DocumentDrawer docId={drawer?.docId ?? null} chunkId={drawer?.chunkId} onClose={() => setDrawer(null)} />
    </div>
  )
}

const SOURCE_WORDS: [string, string, string][] = [
  ['meeting', 'meeting transcript', 'meeting transcripts'],
  ['docx', 'Word document', 'Word documents'],
  ['pptx', 'slide deck', 'slide decks'],
  ['xlsx', 'spreadsheet', 'spreadsheets'],
]

function Welcome({ counts, onPick }: { counts: Record<string, number> | null; onPick: (text: string) => void }) {
  const parts = SOURCE_WORDS.filter(([k]) => counts?.[k]).map(([k, one, many]) => `${counts![k]} ${counts![k] === 1 ? one : many}`)
  const corpus = parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}` : parts[0]
  return (
    <div className="pt-[14vh] pb-8">
      <h1 className="text-[32px] leading-tight font-semibold tracking-tight text-slate-900 dark:text-white">
        What do you need to know?
      </h1>
      <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-slate-600 dark:text-slate-400">
        Answers come from {corpus ?? "FastChip's meetings and documents"}. Each statement names its source file and
        the people behind it. If the sources don't settle a question, you'll get the right person to ask.
      </p>
      <div className="mt-8">
        <h2 className="mb-2 text-xs font-medium text-slate-500">Try asking</h2>
        <ul className="divide-y divide-slate-200/80 border-y border-slate-200/80 dark:divide-slate-800 dark:border-slate-800">
          {SUGGESTIONS.map((s) => (
            <li key={s.text}>
              <button
                onClick={() => onPick(s.text)}
                className="group flex w-full items-center gap-3 py-2.5 text-left text-sm text-slate-700 transition-colors hover:text-brand-700 dark:text-slate-300 dark:hover:text-brand-200"
              >
                <span className="text-slate-400 group-hover:text-brand-600">{s.icon}</span>
                <span className="flex-1">{s.text}</span>
                <CornerDownLeft className="size-3.5 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
