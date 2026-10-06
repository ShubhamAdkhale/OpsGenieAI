import { Link } from 'react-router-dom'
import { formatInr } from '../services/api.js'
import { riskChip, riskDot } from './RiskBadge.jsx'

/**
 * The first thing on the screen, and for ten seconds the only thing that
 * matters. It answers, in this order:
 *
 *   WHAT is wrong  ->  WHAT will happen  ->  HOW MUCH  ->  WHY  ->  WHAT to do
 *
 * Every string and every rupee figure is rendered verbatim from the backend's
 * `priority` payload. This component does no ranking, no thresholding and no
 * arithmetic — if a number appears here, `services/priority.py` computed it.
 *
 * Previous version had a coloured gradient wash, a coloured glow shadow, seven
 * type sizes and a four-column restatement of facts already shown above. All
 * of it has gone. Severity is now carried by ONE element — a coloured rule down
 * the left edge plus the badge — so the card reads as a document rather than an
 * alarm, and the two numbers that matter are the largest things in it.
 */

const SEVERITY_RULE = {
  CRITICAL: 'before:bg-status-critical',
  HIGH: 'before:bg-status-serious',
  MODERATE: 'before:bg-status-warn',
  LOW: 'before:bg-status-good',
  NORMAL: 'before:bg-status-good',
}

/** The calm state. A control tower with nothing wrong should say so plainly. */
function AllClear({ summary }) {
  return (
    <section className="card card-pad relative overflow-hidden pl-6 before:absolute before:inset-y-0 before:left-0 before:w-1.5 before:bg-status-good before:content-['']">
      <div className="flex flex-wrap items-center gap-3">
        <span className="h-2 w-2 rounded-full bg-status-good" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-ink-1">{summary.headline}</h2>
        <span className="ml-auto text-xs text-ink-3">Nothing needs a decision</span>
      </div>
      <p className="mt-1.5 text-sm text-ink-2">{summary.answers?.what_will_happen}</p>
      {summary.recommendation?.text && (
        <p className="mt-2 text-xs text-ink-3">{summary.recommendation.text}</p>
      )}
    </section>
  )
}

export default function PrioritySummary({ summary, onApprove, onReject, busy }) {
  if (!summary) return null
  if (summary.state !== 'ATTENTION') return <AllClear summary={summary} />

  const {
    severity,
    headline,
    subject,
    prediction,
    financial,
    causes = [],
    equipment,
    recommendation,
  } = summary
  const rule = SEVERITY_RULE[severity] ?? SEVERITY_RULE.MODERATE
  const canApprove = recommendation?.requires_approval && recommendation?.workflow_id

  return (
    <section
      className={`card relative overflow-hidden before:absolute before:inset-y-0 before:left-0 before:w-1.5 before:content-[''] ${rule}`}
    >
      <div className="p-5 pl-6">
        {/* WHAT is wrong */}
        <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
          <div className="min-w-[18rem] flex-1">
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${riskChip(
                  subject.status,
                )}`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${riskDot(subject.status)}`}
                  aria-hidden="true"
                />
                {severity}
              </span>
              <span className="text-xs text-ink-3">
                Melt Index <span className="num font-semibold text-ink-2">{subject.melt_index}</span>
              </span>
            </div>

            <h2 className="mt-2 text-xl font-semibold leading-snug text-ink-1">{headline}</h2>
            <p className="mt-1 text-sm text-ink-3">
              {subject.product} · {subject.lane}
            </p>
          </div>

          {/* WHAT will happen + HOW MUCH is at risk. The two biggest numbers
              on the page, because they are the two that decide whether the
              reader keeps reading. */}
          <div className="flex gap-8">
            <div>
              <p className="field-label">{prediction.label}</p>
              <p className="mt-0.5 text-3xl font-semibold leading-none text-ink-1">
                {prediction.probability_display}
              </p>
            </div>
            <div>
              <p className="field-label">Expected loss</p>
              <p className="mt-0.5 text-3xl font-semibold leading-none text-status-ink-critical">
                {formatInr(financial.expected_loss_inr, { compact: true })}
              </p>
              <p className="mt-1 text-[11px] text-ink-3">{financial.working}</p>
            </div>
          </div>
        </div>

        {/* WHY — plain prose, not chips. The point is to be read, and the
            per-component point values live on the shipment detail page. */}
        <p className="mt-4 text-sm leading-relaxed text-ink-2">
          <span className="font-medium text-ink-1">Why:</span>{' '}
          {causes.length > 0
            ? causes.map((c) => c.component.toLowerCase()).join(', ')
            : 'multiple factors'}
          {subject.cargo_temperature_c != null && (
            <>
              {' · cargo at '}
              <span className="num">{subject.cargo_temperature_c.toFixed(1)}°C</span>
              {subject.safe_transit_temp_c != null && (
                <span className="text-ink-3"> (safe ≤ {subject.safe_transit_temp_c}°C)</span>
              )}
            </>
          )}
          {' · '}
          <span className="num">{subject.remaining_shelf_life_hours}h</span> shelf life left
          {equipment && (
            <>
              {' · '}
              <Link to="/machines" className="text-status-ink-info hover:underline">
                {equipment.code} at {Math.round(equipment.health_score)}% health
              </Link>
            </>
          )}
        </p>
      </div>

      {/* WHAT should I do — the action sits in its own band, so the eye can
          jump straight to it without re-reading the diagnosis. */}
      <div className="border-t border-line bg-surface-sunken px-5 py-4 pl-6">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-[20rem] flex-1">
            <p className="field-label">
              Recommended action
              {recommendation.confidence && (
                <span className="ml-2 normal-case tracking-normal text-ink-3">
                  {recommendation.confidence.toLowerCase()} confidence
                </span>
              )}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-ink-1">{recommendation.text}</p>
            {recommendation.gate_reason && (
              <p className="mt-1.5 text-xs leading-relaxed text-ink-3">
                {recommendation.gate_reason}
              </p>
            )}
          </div>

          {financial.loss_avoided_inr > 0 && (
            <div>
              <p className="field-label">Loss avoided if approved</p>
              <p className="mt-0.5 text-2xl font-semibold leading-none text-status-ink-good">
                {formatInr(financial.loss_avoided_inr, { compact: true })}
              </p>
              <p className="mt-1 text-[11px] text-ink-3">
                {formatInr(financial.expected_loss_inr, { compact: true })} →{' '}
                {formatInr(financial.residual_loss_inr, { compact: true })}
              </p>
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {canApprove ? (
            <>
              <button
                type="button"
                onClick={() => onApprove?.(recommendation.workflow_id)}
                disabled={busy}
                className="btn-approve"
              >
                {busy ? 'Executing…' : 'Approve'}
              </button>
              <button
                type="button"
                onClick={() => onReject?.(recommendation.workflow_id)}
                disabled={busy}
                className="btn-ghost"
              >
                Reject
              </button>
            </>
          ) : (
            <span className="rounded-md border border-line bg-surface-card px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-ink-3">
              {recommendation.status?.replace(/_/g, ' ') ?? 'Monitoring'}
            </span>
          )}
          <Link
            to={`/shipments/${subject.id}`}
            className="ml-auto text-xs text-status-ink-info hover:underline"
          >
            Open {subject.code} →
          </Link>
        </div>
      </div>
    </section>
  )
}
