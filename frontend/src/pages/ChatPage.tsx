import { MessageSquarePlus, MessagesSquare, Sparkles, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, streamChat } from '../api/client'
import { AssistantMessage, Composer, SUGGESTIONS, UserBubble, type UiMessage } from '../components/chat'
import { DocumentDrawer } from '../components/citations'
import { cn, Spinner } from '../components/ui'
import { relativeTime } from '../lib/format'
import type { AnswerPayload, Citation, Conversation, QueryFilters, StoredMessage } from '../types'

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
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [threshold, setThreshold] = useState(0.55)
  const [drawer, setDrawer] = useState<{ docId: string; chunkId: string } | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const createdHere = useRef<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const refreshConversations = useCallback(() => {
    api.conversations().then(setConversations).catch(() => {})
  }, [])

  useEffect(() => {
    refreshConversations()
    api.stats().then((s) => setThreshold(s.confidence_threshold)).catch(() => {})
  }, [refreshConversations])

  useEffect(() => {
    if (!conversationId) {
      if (!streaming) setMessages([])
      return
    }
    if (createdHere.current === conversationId) return // just created by our own stream
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

  const remove = async (id: string) => {
    await api.deleteConversation(id)
    if (id === conversationId) navigate('/chat')
    refreshConversations()
  }

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white/60 md:flex dark:border-slate-800 dark:bg-slate-900/40">
        <div className="p-3">
          <Link
            to="/chat"
            onClick={() => {
              createdHere.current = null
              setMessages([])
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white py-2 text-sm font-medium shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            <MessageSquarePlus className="size-4" /> New chat
          </Link>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 && <p className="px-2 py-4 text-xs text-slate-400">No conversations yet</p>}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={cn(
                'group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm',
                c.id === conversationId
                  ? 'bg-slate-200/70 dark:bg-slate-800'
                  : 'hover:bg-slate-100 dark:hover:bg-slate-800/60',
              )}
            >
              <Link to={`/chat/${c.id}`} className="min-w-0 flex-1" onClick={() => (createdHere.current = null)}>
                <p className="truncate">{c.title}</p>
                <p className="text-[11px] text-slate-400">{relativeTime(c.updated_at)}</p>
              </Link>
              <button
                onClick={() => remove(c.id)}
                className="rounded p-1 text-slate-400 opacity-0 group-hover:opacity-100 hover:text-rose-600"
                title="Delete conversation"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-6">
            {loading && (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            )}
            {!loading && messages.length === 0 && <Welcome onPick={(t) => send(t, null)} />}
            <div className="space-y-6">
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
        <div className="mx-auto w-full max-w-3xl px-4 pb-4">
          <Composer onSend={send} disabled={streaming} onStop={() => abortRef.current?.abort()} />
          <p className="mt-2 text-center text-[11px] text-slate-400">
            Answers cite meetings and documents. Hover a citation for the source; click to open it.
          </p>
        </div>
      </div>
      <DocumentDrawer docId={drawer?.docId ?? null} chunkId={drawer?.chunkId} onClose={() => setDrawer(null)} />
    </div>
  )
}

function Welcome({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center pt-10 pb-8 text-center">
      <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-lg shadow-brand-500/30">
        <Sparkles className="size-6" />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight">Ask FastChip's knowledge base</h1>
      <p className="mt-2 max-w-md text-sm text-slate-500 dark:text-slate-400">
        Answers come from meeting transcripts and Office documents, with citations to the source file and the
        people involved. When I'm not sure, I'll suggest who to ask.
      </p>
      <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.text}
            onClick={() => onPick(s.text)}
            className="flex items-start gap-2.5 rounded-xl border border-slate-200 bg-white p-3 text-left text-sm shadow-sm transition hover:border-brand-500 hover:shadow dark:border-slate-800 dark:bg-slate-900"
          >
            <span className="mt-0.5 text-brand-600 dark:text-brand-100">{s.icon}</span>
            <span>{s.text}</span>
          </button>
        ))}
      </div>
      <p className="mt-6 flex items-center gap-1.5 text-xs text-slate-400">
        <MessagesSquare className="size-3.5" /> Follow-up questions keep the conversation context.
      </p>
    </div>
  )
}
