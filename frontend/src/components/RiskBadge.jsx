/**
 * The single source of status colour in the app.
 *
 * Two deliberate changes from the old version:
 *
 * 1. **Four tiers, not six.** SAFE and LOW were separate greens, MODERATE and
 *    HIGH separate ambers. A reader cannot reliably rank six colours at a
 *    glance, so the extra steps cost attention and bought nothing — the band
 *    name is written next to the colour anyway. The tiers now map to the four
 *    decisions a manager actually makes: fine / watch / act soon / act now.
 *
 * 2. **Colour is never alone.** Every badge carries its label, and a dot marks
 *    the tier, so the status survives colourblindness, greyscale printing and
 *    forced-colors mode. Status hues are reserved: they never stand in for a
 *    chart series.
 *
 * Fill steps are saturated for marks; text uses the darker `status-ink` step,
 * because several fill steps sit under 3:1 on a white surface.
 */

const TIERS = {
  SAFE: 'good',
  LOW: 'good',
  MODERATE: 'warn',
  HIGH: 'serious',
  CRITICAL: 'critical',
  // Machine statuses reuse the same four tiers.
  HEALTHY: 'good',
  WARNING: 'warn',
  // Terminal/neutral states are informational, not a severity.
  REROUTED: 'info',
  DELIVERED: 'neutral',
  INSUFFICIENT_DATA: 'neutral',
}

const TIER_STYLE = {
  good: {
    hex: '#0ca30c',
    chip: 'border-status-good/35 bg-status-good/10 text-status-ink-good',
    dot: 'bg-status-good',
  },
  warn: {
    hex: '#fab219',
    chip: 'border-status-warn/45 bg-status-warn/15 text-status-ink-warn',
    dot: 'bg-status-warn',
  },
  serious: {
    hex: '#ec835a',
    chip: 'border-status-serious/45 bg-status-serious/15 text-status-ink-serious',
    dot: 'bg-status-serious',
  },
  critical: {
    hex: '#d03b3b',
    chip: 'border-status-critical/40 bg-status-critical/10 text-status-ink-critical',
    dot: 'bg-status-critical',
  },
  info: {
    hex: '#2a78d6',
    chip: 'border-status-info/35 bg-status-info/10 text-status-ink-info',
    dot: 'bg-status-info',
  },
  neutral: {
    hex: '#87867f',
    chip: 'border-line-strong bg-surface-sunken text-ink-3',
    dot: 'bg-ink-3',
  },
}

function tierFor(status) {
  return TIER_STYLE[TIERS[status] ?? 'neutral'] ?? TIER_STYLE.neutral
}

export function riskColor(status) {
  return tierFor(status).hex
}

export function riskChip(status) {
  return tierFor(status).chip
}

export function riskDot(status) {
  return tierFor(status).dot
}

export default function RiskBadge({ status, value, size = 'md', showDot = true }) {
  const label = (status ?? 'UNKNOWN').replace(/_/g, ' ')
  const tier = tierFor(status)
  const sizes = {
    sm: 'text-[10px] px-1.5 py-0.5 gap-1',
    md: 'text-xs px-2 py-0.5 gap-1.5',
    lg: 'text-sm px-2.5 py-1 gap-1.5',
  }

  return (
    <span
      className={`inline-flex items-center rounded-md border font-semibold ${sizes[size]} ${tier.chip}`}
    >
      {showDot && (
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tier.dot}`} aria-hidden="true" />
      )}
      {label}
      {value != null && <span className="num font-normal opacity-70">{value}</span>}
    </span>
  )
}
