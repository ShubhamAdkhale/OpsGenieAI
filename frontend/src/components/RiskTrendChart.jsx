import { useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState } from './ui.jsx'
import { TIME_ZONE } from '../services/api.js'

/**
 * How the risk got where it is, and what is driving it.
 *
 * The old version drew five series on one plot — Melt Index plus four risk
 * components — which is exactly the anti-pattern where eight categorical hues
 * are spent on a story that is really one number. Nobody read four faint
 * overlapping lines.
 *
 * It is now two plots doing one job each:
 *
 *   1. **Trend** — a single Melt Index series. One series needs no legend (the
 *      title names it) and no colour coding, so the severity bands behind it
 *      carry all the colour and the line stays a single calm hue.
 *   2. **Drivers** — a horizontal bar of the current weighted contributions,
 *      directly labelled. "Why is it 81?" is a ranking question, and a bar
 *      chart answers ranking questions better than a time series ever will.
 *
 * Both read off the RiskAssessment audit trail the backend already writes, so
 * they cannot disagree with the explainability panel.
 */

const SERIES_1 = '#2a78d6'
const INK_3 = '#87867f'
const GRID = '#ecebe6'
const AXIS = '#cfcec8'

// The same thresholds risk_engine.BANDS uses, drawn as recessive background
// zones rather than dashed lines (dashed grid reads as "projection").
const BANDS = [
  { from: 0, to: 20, fill: '#0ca30c', label: 'Safe' },
  { from: 20, to: 40, fill: '#0ca30c', label: 'Low' },
  { from: 40, to: 60, fill: '#fab219', label: 'Moderate' },
  { from: 60, to: 80, fill: '#ec835a', label: 'High' },
  { from: 80, to: 100, fill: '#d03b3b', label: 'Critical' },
]

const DRIVERS = [
  { key: 'temperature_risk', name: 'Temperature' },
  { key: 'refrigeration_risk', name: 'Refrigeration' },
  { key: 'traffic_risk', name: 'Traffic' },
  { key: 'weather_risk', name: 'Weather' },
]

const AXIS_STYLE = {
  stroke: AXIS,
  tick: { fill: INK_3, fontSize: 11 },
  tickLine: false,
}

const TOOLTIP_STYLE = {
  contentStyle: {
    background: '#ffffff',
    border: '1px solid #e5e4df',
    borderRadius: 8,
    fontSize: 12,
    boxShadow: '0 2px 8px -2px rgba(22,22,26,0.12)',
  },
  labelStyle: { color: '#52514e', fontSize: 11 },
}

function makeTimeTick(series) {
  const first = new Date(series[0]?.computed_at).getTime()
  const last = new Date(series[series.length - 1]?.computed_at).getTime()
  // Under an hour of history, minutes alone repeat across adjacent ticks and
  // the axis reads as nine copies of the same label.
  const withSeconds = Number.isFinite(first) && Number.isFinite(last) && last - first < 3600_000
  return (value) => {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    return date.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      ...(withSeconds ? { second: '2-digit' } : {}),
      hour12: false,
      timeZone: TIME_ZONE,
    })
  }
}

function bandName(value) {
  return BANDS.find((b) => value <= b.to)?.label ?? 'Critical'
}

/** Plot 1: one series, severity bands behind it. */
function Trend({ series, height }) {
  const timeTick = makeTimeTick(series)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
        {/* Bands first, so the data draws on top of them. */}
        {BANDS.map((band) => (
          <ReferenceArea
            key={band.label}
            y1={band.from}
            y2={band.to}
            fill={band.fill}
            fillOpacity={0.05}
            stroke="none"
          />
        ))}
        {[20, 40, 60, 80].map((y) => (
          <ReferenceLine key={y} y={y} stroke={GRID} strokeWidth={1} />
        ))}

        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="computed_at" tickFormatter={timeTick} minTickGap={110} {...AXIS_STYLE} />
        <YAxis domain={[0, 100]} ticks={[0, 20, 40, 60, 80, 100]} {...AXIS_STYLE} />
        <Tooltip
          {...TOOLTIP_STYLE}
          labelFormatter={timeTick}
          formatter={(value) => [`${value} — ${bandName(value)}`, 'Melt Index']}
        />

        <Area
          type="monotone"
          dataKey="melt_index"
          name="Melt Index"
          stroke={SERIES_1}
          strokeWidth={2}
          fill="none"
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#ffffff' }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Plot 2: current drivers, ranked, directly labelled. */
function Drivers({ latest, height }) {
  const rows = DRIVERS.map((driver) => ({
    name: driver.name,
    value: Math.round(latest[driver.key] ?? 0),
  }))
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value)

  if (!rows.length) {
    return <EmptyState>No risk component is currently contributing.</EmptyState>
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          axisLine={false}
          tickLine={false}
          tick={{ fill: '#52514e', fontSize: 12 }}
        />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [`${value} / 100`, 'Component risk']} />
        {/* One series, one colour — never a value-ramp on named categories. */}
        <Bar dataKey="value" fill={SERIES_1} radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false}>
          {rows.map((row) => (
            <Cell key={row.name} />
          ))}
          <LabelList
            dataKey="value"
            position="right"
            offset={8}
            style={{ fill: '#52514e', fontSize: 11 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function RiskTrendChart({ trend, current, height = 240 }) {
  const [view, setView] = useState('trend')
  const series = trend?.series ?? []

  if (series.length < 2) {
    return (
      <EmptyState>
        Not enough history yet — the trend appears once the risk score starts moving.
      </EmptyState>
    )
  }

  const latest = series[series.length - 1]
  // Prefer the live figure the priority card is quoting. The audit trail is
  // written per tick, so its last row can be a few points behind the current
  // evaluation - and showing 57 here under a header that says 61 for the same
  // shipment is the kind of small contradiction that costs all the trust the
  // rest of the page earns.
  const reading = Math.round(current ?? latest.melt_index)

  return (
    <div>
      {/* Hero reading first, so the chart is context rather than a puzzle. */}
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-3xl font-semibold leading-none text-ink-1">{reading}</p>
          <p className="mt-1 text-xs text-ink-3">
            Melt Index now · {bandName(reading)} band
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-line p-0.5">
          {[
            ['trend', 'Trend'],
            ['drivers', 'Drivers'],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setView(key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                view === key
                  ? 'bg-surface-sunken text-ink-1'
                  : 'text-ink-3 hover:text-ink-2'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {view === 'trend' ? (
        <Trend series={series} height={height} />
      ) : (
        <Drivers latest={latest} height={height} />
      )}
    </div>
  )
}
