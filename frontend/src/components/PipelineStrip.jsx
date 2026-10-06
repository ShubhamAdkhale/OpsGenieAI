import { formatInr, formatPercent } from '../services/api.js'
import { ProvenanceLabel } from './ProvenanceStrip.jsx'

/**
 * SENSE → PREDICT → QUANTIFY → DECIDE → ACT, with the live value at each stage.
 *
 * The pipeline is the product's whole argument, and until now it only existed
 * in the README. This strip makes it the first thing a visitor reads: five
 * boxes, each carrying a real number from the dashboard payload, so the chain
 * from a sensor to a rupee to an action is visible without a presenter.
 *
 * Like the priority card, it does no ranking or arithmetic of its own — every
 * value is read straight off `/api/dashboard`.
 */

function Stage({ step, title, value, detail, tone = 'neutral', extra }) {
  const ring = {
    neutral: 'border-line',
    attention: 'border-status-serious/60 bg-status-serious/5',
    good: 'border-status-good/45 bg-status-good/5',
  }[tone]
  return (
    <li className={`relative flex min-w-0 flex-1 flex-col rounded-lg border bg-surface-card px-3.5 py-3 ${ring}`}>
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink-1 text-[10px] font-semibold text-white">
          {step}
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-2">{title}</span>
        {extra && <span className="ml-auto">{extra}</span>}
      </div>
      <p className="mt-2 truncate text-base font-semibold text-ink-1" title={value}>
        {value}
      </p>
      <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-ink-3">{detail}</p>
    </li>
  )
}

function Arrow() {
  return (
    <li aria-hidden="true" className="hidden shrink-0 items-center text-ink-3 lg:flex">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M3 8h9m0 0L8.5 4.5M12 8l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </li>
  )
}

export default function PipelineStrip({ data }) {
  if (!data) return null
  const { kpis = {}, machines = [], shipments = [], priority, provenance, workflow_activity: wf = {} } = data

  const weather = provenance?.streams?.find((s) => s.name === 'Weather')
  const attention = priority?.state === 'ATTENTION'
  const subject = priority?.subject
  // The API returns machines sorted by health, worst first.
  const worstMachine = machines[0]
  const pending = kpis.pending_approvals ?? 0

  const predict = attention
    ? {
        value: `${priority.prediction?.probability_display ?? '—'} spoilage`,
        detail: `${subject.code} · ${subject.product} · ${kpis.shipments_at_risk ?? 0} loads high or critical`,
      }
    : worstMachine
      ? {
          value:
            worstMachine.ml_failure_probability == null
              ? `${formatPercent(worstMachine.failure_probability)} condition risk`
              : `${formatPercent(worstMachine.ml_failure_probability)} failure risk <24h`,
          detail: `${worstMachine.code}, the least healthy unit (${Math.round(worstMachine.health_score)}% health) · no load at risk`,
        }
      : { value: '—', detail: 'No units monitored' }

  const decide = attention
    ? {
        value: priority.recommendation?.requires_approval ? 'Awaiting approval' : 'Recommendation ready',
        detail: priority.recommendation?.text,
      }
    : {
        value: pending ? `${pending} awaiting approval` : 'Nothing to decide',
        detail: pending ? 'Maintenance or reroute actions queued' : 'Every load is inside its safe envelope',
      }

  return (
    <section aria-label="Decision pipeline">
      <ol className="flex flex-col gap-2 lg:flex-row lg:items-stretch">
        <Stage
          step={1}
          title="Sense"
          value={`${machines.length} units · ${shipments.length} loads on the road`}
          detail={`${kpis.delivered ?? 0} delivered this episode (${kpis.delivered_in_spec ?? 0} in spec) · ${kpis.machines_at_risk ?? 0} units need attention`}
          extra={weather && <ProvenanceLabel label={weather.label} />}
        />
        <Arrow />
        <Stage step={2} title="Predict" value={predict.value} detail={predict.detail} tone={attention ? 'attention' : 'neutral'} />
        <Arrow />
        <Stage
          step={3}
          title="Quantify"
          value={formatInr(kpis.value_at_risk_inr, { compact: true })}
          detail={`Expected loss across ${kpis.active_shipments ?? 0} active loads (value × spoilage probability)`}
          tone={attention ? 'attention' : 'neutral'}
        />
        <Arrow />
        <Stage step={4} title="Decide" value={decide.value} detail={decide.detail} tone={attention || pending ? 'attention' : 'neutral'} />
        <Arrow />
        <Stage
          step={5}
          title="Act"
          value={`${formatInr(kpis.loss_avoided_inr, { compact: true })} saved`}
          detail={`${wf.auto_executed ?? 0} auto-executed · ${wf.executed ?? 0} approved by a manager`}
          tone={kpis.loss_avoided_inr > 0 ? 'good' : 'neutral'}
        />
      </ol>
    </section>
  )
}
