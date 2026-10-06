/** One top-level number + label + optional trend arrow (§28). */

export default function KpiCard({
  label,
  value,
  sub,
  tone = 'neutral',
  trend,
  icon,
}) {
  const tones = {
    neutral: 'text-ink-1',
    good: 'text-status-ink-good',
    warn: 'text-status-ink-warn',
    bad: 'text-status-ink-critical',
    info: 'text-status-ink-info',
  }
  const trendMark =
    trend === undefined || trend === null || trend === 0
      ? null
      : trend > 0
        ? { glyph: '▲', cls: 'text-status-ink-critical' }
        : { glyph: '▼', cls: 'text-status-ink-good' }

  return (
    <div className="card card-pad">
      <div className="flex items-start justify-between gap-2">
        <p className="card-title">{label}</p>
        {icon && <span className="text-base leading-none opacity-70">{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`text-2xl font-semibold num ${tones[tone]}`}>{value}</span>
        {trendMark && (
          <span className={`text-xs font-semibold ${trendMark.cls}`}>
            {trendMark.glyph} {Math.abs(trend)}
          </span>
        )}
      </div>
      {sub && <p className="mt-1 text-xs text-ink-3">{sub}</p>}
    </div>
  )
}
