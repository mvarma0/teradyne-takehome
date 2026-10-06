import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Conversation } from '../types'
import { ConversationsContext } from './conversationsContext'

/** Conversation list shared by the navigation (recent questions) and the chat page. */
export function ConversationsProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const refresh = useCallback(() => {
    api.conversations().then(setConversations).catch(() => {})
  }, [])
  const remove = useCallback(
    async (id: string) => {
      await api.deleteConversation(id)
      refresh()
    },
    [refresh],
  )
  useEffect(refresh, [refresh])
  return <ConversationsContext.Provider value={{ conversations, refresh, remove }}>{children}</ConversationsContext.Provider>
}
