import { createContext, useContext } from 'react'
import type { Conversation } from '../types'

export interface ConversationsCtx {
  conversations: Conversation[]
  refresh: () => void
  remove: (id: string) => Promise<void>
}

export const ConversationsContext = createContext<ConversationsCtx>({
  conversations: [],
  refresh: () => {},
  remove: async () => {},
})

export const useConversations = () => useContext(ConversationsContext)
