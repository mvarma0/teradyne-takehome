import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setStatus(d.status))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <main className="min-h-screen bg-slate-50 p-8 text-slate-900">
      <h1 className="text-2xl font-semibold">FastChip Knowledge Assistant</h1>
      <p className="mt-2 text-sm text-slate-600">backend: {status}</p>
    </main>
  )
}
