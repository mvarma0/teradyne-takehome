import { Activity, ClipboardCheck, FileStack, FlaskConical, GitBranch, Info, MessagesSquare, Moon, Plus, Sun, Trash2, UserRound } from 'lucide-react'
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api } from './api/client'
import { Logo } from './components/brand'
import { cn, Spinner } from './components/ui'
import { ConversationsProvider } from './lib/conversations'
import { useConversations } from './lib/conversationsContext'
import { getUserName, setUserName } from './lib/format'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'
import DocumentViewerPage from './pages/DocumentViewerPage'
import ReviewPage from './pages/ReviewPage'

const MonitoringPage = lazy(() => import('./pages/MonitoringPage'))
const EvalsPage = lazy(() => import('./pages/EvalsPage'))
const TracePage = lazy(() => import('./pages/TracePage'))
const AboutPage = lazy(() => import('./pages/AboutPage'))

const NAV = [
  { to: '/chat', label: 'Ask', icon: MessagesSquare },
  { to: '/documents', label: 'Documents', icon: FileStack },
  { to: '/trace', label: 'Traceability', icon: GitBranch },
  { to: '/review', label: 'Review queue', icon: ClipboardCheck, badge: true },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/evals', label: 'Evals', icon: FlaskConical },
  { to: '/about', label: 'About', icon: Info },
]

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try {
      localStorage.setItem('fastchip.theme', dark ? 'dark' : 'light')
    } catch {
      /* storage unavailable */
    }
  }, [dark])
  return [dark, setDark] as const
}

function Shell({ children }: { children: ReactNode }) {
  const [dark, setDark] = useTheme()
  const [pending, setPending] = useState(0)
  const [name, setName] = useState(getUserName())
  useEffect(() => {
    const load = () => api.reviewQueue({ status: 'pending' }).then((q) => setPending(q.counts.pending)).catch(() => {})
    load()
    const t = window.setInterval(load, 15000)
    return () => window.clearInterval(t)
  }, [])
  return (
    <div className="flex h-full">
      <nav className="flex w-16 shrink-0 flex-col items-center border-r border-slate-200/90 bg-white py-4 lg:w-60 lg:items-stretch lg:px-3 dark:border-slate-800 dark:bg-[#0f171a]">
        <Link to="/chat" className="mb-6 flex items-center gap-2.5 px-1 lg:px-2" aria-label="FastChip knowledge base">
          <Logo className="size-8 shrink-0" />
          <div className="hidden lg:block">
            <p className="text-[15px] leading-tight font-semibold tracking-tight">FastChip</p>
            <p className="text-xs leading-tight text-slate-500">Knowledge base</p>
          </div>
        </Link>
        <div className="flex flex-col gap-0.5">
          {NAV.map(({ to, label, icon: Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={to !== '/chat' && to !== '/trace'}
              title={label}
              className={({ isActive }) =>
                cn(
                  'relative flex items-center gap-2.5 rounded-md p-2 text-sm transition-colors lg:px-2.5',
                  isActive
                    ? 'bg-slate-100 font-medium text-slate-900 dark:bg-slate-800 dark:text-white'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-100',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute top-2 bottom-2 left-0 hidden w-0.5 rounded-full bg-brand-600 lg:block" />}
                  <Icon className={cn('size-[18px] shrink-0', isActive && 'text-brand-600 dark:text-brand-200')} />
                  <span className="hidden lg:inline">{label}</span>
                  {badge && pending > 0 && (
                    <span
                      className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white lg:static lg:ml-auto lg:h-5 lg:min-w-5 lg:bg-amber-100 lg:text-amber-800 dark:lg:bg-amber-900/50 dark:lg:text-amber-200"
                      title={`${pending} pending review`}
                    >
                      {pending}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>
        <RecentConversations />
        <div className="mt-auto space-y-1 border-t border-slate-200/80 pt-3 dark:border-slate-800">
          <label
            className="hidden items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-slate-500 lg:flex"
            title="Recorded when you send a routed question or submit a correction"
          >
            <UserRound className="size-3.5 shrink-0" />
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setUserName(e.target.value)
              }}
              placeholder="Your name"
              aria-label="Your name"
              className="w-full bg-transparent text-slate-700 outline-none placeholder:text-slate-400 dark:text-slate-200"
            />
          </label>
          <button
            onClick={() => setDark(!dark)}
            className="flex w-full items-center justify-center gap-2 rounded-md p-2 text-sm text-slate-500 hover:bg-slate-50 lg:justify-start lg:px-2.5 dark:hover:bg-slate-800/60"
            title="Toggle theme"
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            <span className="hidden lg:inline">{dark ? 'Light' : 'Dark'} theme</span>
          </button>
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}

function RecentConversations() {
  const { conversations, remove } = useConversations()
  const navigate = useNavigate()
  const location = useLocation()
  const current = location.pathname.match(/^\/chat\/(.+)$/)?.[1]
  return (
    <div className="mt-6 hidden min-h-0 flex-1 flex-col lg:flex">
      <div className="mb-1 flex items-center justify-between px-2.5">
        <h2 className="text-xs font-medium text-slate-500">Recent questions</h2>
        <Link
          to="/chat"
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-900/40"
        >
          <Plus className="size-3.5" /> New
        </Link>
      </div>
      <div className="-mx-1 min-h-0 flex-1 space-y-px overflow-y-auto px-1 pb-2">
        {conversations.length === 0 && <p className="px-2.5 py-2 text-xs text-slate-400">Your questions will appear here.</p>}
        {conversations.slice(0, 30).map((c) => (
          <div
            key={c.id}
            className={cn(
              'group flex items-center rounded-md text-[13px]',
              c.id === current
                ? 'bg-brand-50 text-brand-900 dark:bg-brand-900/40 dark:text-brand-100'
                : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800/60',
            )}
          >
            <Link to={`/chat/${c.id}`} className="min-w-0 flex-1 truncate px-2.5 py-1.5" title={c.title}>
              {c.title}
            </Link>
            <button
              onClick={async () => {
                await remove(c.id)
                if (c.id === current) navigate('/chat')
              }}
              className="mr-1 rounded p-1 text-slate-400 opacity-0 group-hover:opacity-100 hover:text-rose-600 focus:opacity-100"
              title="Delete conversation"
              aria-label={`Delete conversation ${c.title}`}
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

function Page({ children }: { children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-10 lg:px-10">
        <Suspense fallback={<Spinner />}>{children}</Suspense>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ConversationsProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/documents" element={<Page><DocumentsPage /></Page>} />
          <Route path="/documents/:docId" element={<Page><DocumentViewerPage /></Page>} />
          <Route path="/review" element={<Page><ReviewPage /></Page>} />
          <Route path="/monitoring" element={<Page><MonitoringPage /></Page>} />
          <Route path="/evals" element={<Page><EvalsPage /></Page>} />
          <Route path="/trace" element={<Page><TracePage /></Page>} />
          <Route path="/trace/:queryId" element={<Page><TracePage /></Page>} />
          <Route path="/about" element={<Page><AboutPage /></Page>} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </Shell>
      </ConversationsProvider>
    </BrowserRouter>
  )
}
