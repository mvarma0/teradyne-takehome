import { Activity, ClipboardCheck, FileStack, FlaskConical, MessagesSquare, Moon, Sparkles, Sun, UserRound } from 'lucide-react'
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api/client'
import { cn, Spinner } from './components/ui'
import { getUserName, setUserName } from './lib/format'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'
import DocumentViewerPage from './pages/DocumentViewerPage'
import ReviewPage from './pages/ReviewPage'

const MonitoringPage = lazy(() => import('./pages/MonitoringPage'))
const EvalsPage = lazy(() => import('./pages/EvalsPage'))

const NAV = [
  { to: '/chat', label: 'Chat', icon: MessagesSquare },
  { to: '/documents', label: 'Documents', icon: FileStack },
  { to: '/review', label: 'Review queue', icon: ClipboardCheck, badge: true },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/evals', label: 'Evals', icon: FlaskConical },
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
      <nav className="flex w-16 shrink-0 flex-col items-center border-r border-slate-200 bg-white py-3 lg:w-56 lg:items-stretch lg:px-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-6 flex items-center gap-2 px-1 lg:px-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-sm">
            <Sparkles className="size-4" />
          </div>
          <div className="hidden lg:block">
            <p className="text-sm leading-tight font-semibold">FastChip</p>
            <p className="text-[11px] leading-tight text-slate-500">Knowledge Assistant</p>
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              title={label}
              className={({ isActive }) =>
                cn(
                  'relative flex items-center gap-2.5 rounded-lg p-2 text-sm font-medium transition lg:px-2.5',
                  isActive
                    ? 'bg-brand-50 text-brand-700 dark:bg-brand-700/20 dark:text-brand-100'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                )
              }
            >
              <Icon className="size-[18px] shrink-0" />
              <span className="hidden lg:inline">{label}</span>
              {badge && pending > 0 && (
                <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white lg:static lg:ml-auto">
                  {pending}
                </span>
              )}
            </NavLink>
          ))}
        </div>
        <div className="space-y-2 border-t border-slate-100 pt-3 dark:border-slate-800">
          <label className="hidden items-center gap-2 rounded-lg px-2 py-1 text-xs text-slate-500 lg:flex" title="Used when you send questions or submit corrections">
            <UserRound className="size-3.5 shrink-0" />
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setUserName(e.target.value)
              }}
              placeholder="Your name"
              className="w-full bg-transparent outline-none placeholder:text-slate-400"
            />
          </label>
          <button
            onClick={() => setDark(!dark)}
            className="flex w-full items-center justify-center gap-2 rounded-lg p-2 text-sm text-slate-500 hover:bg-slate-100 lg:justify-start lg:px-2.5 dark:hover:bg-slate-800"
            title="Toggle theme"
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            <span className="hidden lg:inline">{dark ? 'Light' : 'Dark'} mode</span>
          </button>
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}

function Page({ children }: { children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <Suspense fallback={<Spinner />}>{children}</Suspense>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
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
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
