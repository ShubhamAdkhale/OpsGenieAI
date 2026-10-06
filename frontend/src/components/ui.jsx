import { riskColor } from './RiskBadge.jsx'

/** Small shared building blocks used across the five pages. */

export function Section({ title, subtitle, action, children, className = '' }) {
  return (
    <section className={`card card-pad ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Loading({ label = 'Loading…', rows = 3 }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <p className="text-sm text-ink-3">{label}</p>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-12 animate-pulse rounded-card bg-surface-sunken" />
      ))}
    </div>
  )
}

/**
 * A visible banner rather than a blank or broken page. Because usePolling keeps
 * the last good payload, the dashboard stays readable while this shows.
 */
export function ErrorBanner({ error, onRetry }) {
  if (!error) return null
  const unreachable = error.status === 0
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-status-critical/40 bg-status-critical/5 px-4 py-3">
      <div>
        <p className="text-sm font-semibold text-status-ink-critical">
          {unreachable ? 'Backend unreachable' : 'Request failed'}
        </p>
        <p className="mt-0.5 text-xs text-ink-2">
          {unreachable
            ? 'Start the API with: uvicorn app.main:app --reload --port 8000 (from the backend/ folder). Showing the last data received.'
            : error.message}
        </p>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-ghost">
          Retry
        </button>
      )}
    </div>
  )
}

export function Disclaimer({ children }) {
  return (
    <p className="text-xs leading-relaxed text-ink-3">
      {children ??
        'Simulated operational data with live weather. Melt Index, spoilage probability and rupee figures are decision-support estimates, not guarantees.'}
    </p>
  )
}

/** The Melt Index dial on the Shipment Detail page. */
export function MeltIndexDial({ value, status, size = 150 }) {
  const radius = (size - 16) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.max(0, Math.min(100, value ?? 0))
  const color = riskColor(status)

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#ecebe6"
          strokeWidth="9"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          style={{ transition: 'stroke-dashoffset 700ms ease, stroke 700ms ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-semibold text-ink-1">{Math.round(clamped)}</span>
        <span className="mt-0.5 text-[10px] uppercase tracking-wide text-ink-3">
          Melt Index
        </span>
      </div>
    </div>
  )
}

const TILE_TONES = {
  neutral: 'text-ink-1',
  good: 'text-status-ink-good',
  warn: 'text-status-ink-warn',
  bad: 'text-status-ink-critical',
  info: 'text-status-ink-info',
}

export function MetricTile({ label, value, tone = 'neutral', sub }) {
  return (
    <div className="panel">
      <p className="field-label">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${TILE_TONES[tone]}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] leading-snug text-ink-3">{sub}</p>}
    </div>
  )
}

export function EmptyState({ children }) {
  return <p className="py-10 text-center text-sm text-ink-3">{children}</p>
}
