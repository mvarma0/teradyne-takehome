import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, cn } from './ui'

export interface Series {
  key: string
  label: string
  color: string // CSS var, e.g. var(--series-1)
}

const axisProps = {
  stroke: 'var(--chart-axis)',
  tick: { fill: 'var(--chart-axis)', fontSize: 11 },
  tickLine: false,
  axisLine: false,
}

function ChartTooltip({ active, payload, label, format, labelFormat }: {
  active?: boolean
  payload?: { name: string; value: number | null; color: string }[]
  label?: string
  format: (v: number | null) => string
  labelFormat?: (l: string) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
      <p className="mb-1 font-medium text-slate-700 dark:text-slate-200">{labelFormat ? labelFormat(label ?? '') : label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          <span>{p.name}</span>
          <span className="ml-auto font-medium tabular-nums">{format(p.value)}</span>
        </p>
      ))}
    </div>
  )
}

export function ChartCard({ title, subtitle, children, legend }: {
  title: string
  subtitle?: string
  children: ReactNode
  legend?: Series[]
}) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        {legend && legend.length > 1 && (
          <div className="flex flex-wrap gap-3 text-xs text-slate-600 dark:text-slate-300">
            {legend.map((s) => (
              <span key={s.key} className="flex items-center gap-1.5">
                <span className="h-0.5 w-3 rounded" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="h-52">{children}</div>
    </Card>
  )
}

/** Line trend with crosshair tooltip. One y-scale only; multi-series share the same unit. */
export function LineTrend({ data, xKey, series, format, domain, labelFormat }: {
  data: object[]
  xKey: string
  series: Series[]
  format: (v: number | null) => string
  domain?: [number, number]
  labelFormat?: (l: string) => string
}) {
  const last = data.length - 1
  // Direct-label collision avoidance: nudge end labels whose values sit close together.
  const lastRow = (data[last] ?? {}) as Record<string, number | null>
  const span = domain ? domain[1] - domain[0] : 1
  const labelDy = series.map((s, i) => {
    const v = lastRow[s.key]
    if (v === null || v === undefined) return 0
    const close = series.slice(0, i).filter((o) => {
      const w = lastRow[o.key]
      return w !== null && w !== undefined && Math.abs(w - v) < span * 0.07
    }).length
    return close * 13
  })
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: series.length > 1 ? 56 : 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey={xKey} {...axisProps} tickFormatter={labelFormat} minTickGap={24} />
        <YAxis {...axisProps} domain={domain ?? ['auto', 'auto']} tickFormatter={(v) => format(v)} width={56} />
        <Tooltip
          cursor={{ stroke: 'var(--chart-axis)', strokeDasharray: '3 3' }}
          content={<ChartTooltip format={format} labelFormat={labelFormat} />}
        />
        {series.map((s, si) => (
          <Line
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            dot={{ r: 4, strokeWidth: 2, stroke: 'var(--chart-surface)', fill: s.color }}
            activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--chart-surface)' }}
            connectNulls
            isAnimationActive={false}
          >
            {series.length > 1 && (
              <LabelList
                dataKey={s.key}
                content={({ x, y, index }) =>
                  index === last ? (
                    <text x={Number(x) + 8} y={Number(y) + 4 + labelDy[si]} fontSize={11} fill="var(--chart-axis)">
                      {s.label}
                    </text>
                  ) : null
                }
              />
            )}
          </Line>
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function BarTrend({ data, xKey, series, format, labelFormat }: {
  data: object[]
  xKey: string
  series: Series
  format: (v: number | null) => string
  labelFormat?: (l: string) => string
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }} barCategoryGap={2}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey={xKey} {...axisProps} tickFormatter={labelFormat} minTickGap={24} />
        <YAxis {...axisProps} allowDecimals={false} width={56} />
        <Tooltip cursor={{ fill: 'var(--chart-grid)', opacity: 0.5 }} content={<ChartTooltip format={format} labelFormat={labelFormat} />} />
        <Bar dataKey={series.key} name={series.label} fill={series.color} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Hero number with delta vs. baseline. `goodWhen` decides the delta's tone. */
export function StatTile({ label, value, delta, deltaText, goodWhen = 'up', hint, alert }: {
  label: string
  value: string
  delta?: number | null
  deltaText?: string
  goodWhen?: 'up' | 'down'
  hint?: string
  alert?: boolean
}) {
  const hasDelta = delta !== null && delta !== undefined && Number.isFinite(delta) && Math.abs(delta) > 0.0005
  const good = hasDelta && (goodWhen === 'up' ? delta! > 0 : delta! < 0)
  return (
    <Card className={cn('p-4', alert && 'border-rose-300 dark:border-rose-800')}>
      <p className="text-xs text-slate-500" title={hint}>
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      <p className="mt-1 flex items-center gap-1 text-xs">
        {hasDelta ? (
          <span className={cn('flex items-center gap-0.5 font-medium', good ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400')}>
            {delta! > 0 ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}
            {deltaText}
          </span>
        ) : (
          <span className="flex items-center gap-0.5 text-slate-400">
            <Minus className="size-3.5" /> no change
          </span>
        )}
        <span className="text-slate-400">vs previous window</span>
      </p>
    </Card>
  )
}
