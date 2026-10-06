import { Link } from 'react-router-dom'
import RiskBadge, { riskColor } from './RiskBadge.jsx'
import { formatPercent, formatRunway } from '../services/api.js'

/** Health gauge + failure-within-24h + condition risk + status (§28). */

function Gauge({ value, status, size = 76 }) {
  const radius = (size - 10) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.max(0, Math.min(100, value ?? 0))
  const offset = circumference * (1 - clamped / 100)
  const color = riskColor(status)

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e5e4df"
          strokeWidth="6"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-base font-semibold num text-ink-1">
          {Math.round(clamped)}
        </span>
        <span className="text-[9px] uppercase tracking-wider text-ink-3">health</span>
      </div>
    </div>
  )
}

export default function MachineHealthCard({ machine, compact = false }) {
  const critical = machine.failure_probability > 0.75

  return (
    <Link
      to={`/machines?id=${machine.id}`}
      className={`card card-pad block transition-colors hover:border-line-strong ${
        critical ? 'ring-1 ring-status-critical/40' : ''
      }`}
    >
      <div className="flex items-start gap-4">
        <Gauge
          value={machine.health_score}
          status={machine.status}
          size={compact ? 64 : 76}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-mono text-sm font-semibold text-ink-1">{machine.code}</p>
              {/* Two lines rather than one truncated one. At four cards per
                  row "Refrigeration Unit · Nagpur Cold Hub" clipped to
                  "Refrigeration Unit · Na…", which hid the only part that
                  varies between the units. */}
              <p className="text-xs leading-snug text-ink-2">{machine.location}</p>
              <p className="text-[11px] leading-snug text-ink-3">{machine.type_label}</p>
            </div>
            <RiskBadge status={machine.status} size="sm" pulse={critical} />
          </div>

          <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <div>
              {/* The trend-based classifier: will it fail in the next day? */}
              <dt className="text-ink-3">Failure &lt;24h</dt>
              <dd
                className={`font-mono font-semibold num ${
                  machine.ml_failure_probability > 0.5 ? 'text-status-ink-critical' : 'text-ink-2'
                }`}
              >
                {machine.ml_failure_probability == null
                  ? '—'
                  : formatPercent(machine.ml_failure_probability)}
              </dd>
            </div>
            <div>
              {/* The health-based rule that raises workflows: how worn it is. */}
              <dt className="text-ink-3">Condition risk</dt>
              <dd className={`num ${critical ? 'font-semibold text-status-ink-critical' : 'text-ink-2'}`}>
                {formatPercent(machine.failure_probability)}
              </dd>
            </div>
            <div>
              {/* Time to the efficiency floor at the CURRENT rate of decline.
                  A chronically worn unit can be CRITICAL on health yet have a
                  long runway, because it is degrading slowly — so this is
                  labelled for what it measures rather than as "failure in". */}
              <dt className="text-ink-3">Eff. floor in</dt>
              <dd className="num text-ink-2">
                {formatRunway(machine.estimated_failure_hours)}
              </dd>
            </div>
            <div>
              <dt className="text-ink-3">Carrying</dt>
              <dd className="truncate font-mono text-ink-2">
                {machine.assigned_shipments?.length
                  ? machine.assigned_shipments.join(', ')
                  : '—'}
              </dd>
            </div>
          </dl>

          {machine.anomaly_detected && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded border border-status-warn/40 bg-status-warn/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-status-ink-warn">
              Anomaly detected · score {machine.anomaly_score?.toFixed(2)}
            </p>
          )}
        </div>
      </div>
    </Link>
  )
}
