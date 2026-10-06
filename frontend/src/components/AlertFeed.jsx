import { Link } from 'react-router-dom'
import { formatDateTime } from '../services/api.js'

/** Scrollable severity-coloured alert list (§28). */

const SEVERITY = {
  CRITICAL: { bar: 'bg-status-critical', text: 'text-status-ink-critical', label: 'Critical' },
  WARNING: { bar: 'bg-status-warn', text: 'text-status-ink-warn', label: 'Warning' },
  INFO: { bar: 'bg-status-info', text: 'text-status-ink-info', label: 'Info' },
}

function targetLink(alert) {
  if (alert.related_type === 'shipment' && alert.related_id) {
    return `/shipments/${alert.related_id}`
  }
  if (alert.related_type === 'machine' && alert.related_id) {
    return `/machines?id=${alert.related_id}`
  }
  return null
}

export default function AlertFeed({ alerts = [], maxHeight = 340 }) {
  if (!alerts.length) {
    return <p className="py-6 text-center text-sm text-ink-3">No alerts yet.</p>
  }

  return (
    <ul className="space-y-2 overflow-y-auto pr-1" style={{ maxHeight }}>
      {alerts.map((alert) => {
        const tone = SEVERITY[alert.severity] ?? SEVERITY.INFO
        const href = targetLink(alert)
        const body = (
          <div className="flex gap-2.5">
            <span className={`mt-0.5 w-1 shrink-0 rounded-full ${tone.bar}`} aria-hidden="true" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-semibold uppercase tracking-wider ${tone.text}`}>
                  {tone.label}
                </span>
                <span className="text-[10px] text-ink-3">
                  {formatDateTime(alert.created_at)}
                </span>
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-ink-2">{alert.message}</p>
            </div>
          </div>
        )
        return (
          <li
            key={alert.id}
            className="rounded-lg border border-line bg-surface-sunken p-2.5 transition-colors hover:border-line"
          >
            {href ? (
              <Link to={href} className="block">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        )
      })}
    </ul>
  )
}
