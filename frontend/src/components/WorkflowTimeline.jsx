import { formatDateTime, formatInr } from '../services/api.js'

/**
 * Vertical stepper: Recommendation → Reason → Impact → Approval → Executed (§28).
 *
 * The steps are derived from the workflow's own status, so the timeline can
 * never claim a stage the database doesn't record.
 */

const TERMINAL = {
  EXECUTED: { label: 'Executed', tone: 'emerald' },
  OVERRIDDEN: { label: 'Executed with manager override', tone: 'sky' },
  AUTO_EXECUTED: { label: 'Auto-executed', tone: 'emerald' },
  REJECTED: { label: 'Rejected — no action taken', tone: 'rose' },
}

const TONES = {
  emerald: 'border-status-good bg-status-good',
  sky: 'border-status-info bg-status-info',
  rose: 'border-status-critical bg-status-critical',
  amber: 'border-status-warn bg-status-warn',
  slate: 'border-line-strong bg-surface-sunken',
}

function Step({ title, detail, tone = 'slate', done = true, last = false }) {
  return (
    <li className="relative pl-7">
      {!last && <span className="absolute left-[7px] top-4 h-full w-px bg-line" />}
      <span
        className={`absolute left-0 top-1 h-3.5 w-3.5 rounded-full border-2 ${
          done ? TONES[tone] : 'border-line-strong bg-surface-card'
        }`}
      />
      <p className="text-sm font-semibold text-ink-1">{title}</p>
      {detail && <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{detail}</p>}
    </li>
  )
}

export default function WorkflowTimeline({ workflow }) {
  if (!workflow) return null

  const terminal = TERMINAL[workflow.status]
  const pending = workflow.status === 'PENDING_APPROVAL'
  const autoExecuted = workflow.status === 'AUTO_EXECUTED'

  return (
    <ol className="space-y-4">
      <Step
        title={`Recommendation · ${workflow.workflow_type.replace(/_/g, ' ')}`}
        detail={workflow.recommendation_text}
        tone="amber"
      />
      <Step title="Reason" detail={workflow.trigger_reason} tone="amber" />
      <Step
        title={`Impact · ${formatInr(workflow.impact_inr)}`}
        detail={`${workflow.confidence} confidence (margin ${workflow.confidence_score?.toFixed(
          2,
        )}). ${workflow.resolution_note || ''}`}
        tone="amber"
      />
      <Step
        title={
          autoExecuted
            ? 'Approval not required'
            : pending
              ? 'Awaiting manager approval'
              : 'Manager decision recorded'
        }
        detail={
          autoExecuted
            ? 'High confidence and low impact — auto-executed under the decision rules.'
            : pending
              ? 'Approve, reject or override on this page. Approvals are timestamped and immutable.'
              : formatDateTime(workflow.resolved_at)
        }
        tone={pending ? 'slate' : 'sky'}
        done={!pending}
      />
      <Step
        title={terminal ? terminal.label : 'Not yet executed'}
        detail={
          terminal
            ? 'Simulated execution — no external courier, ERP or work-order system was called.'
            : undefined
        }
        tone={terminal ? terminal.tone : 'slate'}
        done={Boolean(terminal)}
        last
      />
    </ol>
  )
}
