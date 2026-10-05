import { useEffect, useState } from 'react'

function App() {
  const [health, setHealth] = useState('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: { status: string }) => setHealth(data.status))
      .catch(() => setHealth('unreachable'))
  }, [])

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold text-slate-900">FastChip Knowledge</h1>
      <p className="mt-2 text-sm text-slate-600">
        backend: <span className={health === 'ok' ? 'text-green-700' : 'text-red-700'}>{health}</span>
      </p>
    </main>
  )
}

export default App
