import { Fragment, useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatDateTime, formatDuration, formatInr, formatPercent } from '../services/api.js'
import { usePolling } from '../hooks/usePolling.js'
import WorkflowTimeline from '../components/WorkflowTimeline.jsx'
import { EmptyState, ErrorBanner, Loading, MetricTile, Section } from '../components/ui.jsx'

/** Page 5 (§27): full workflow history with approve/reject actions. */

const STATUS_STYLE = {
  PENDING_APPROVAL: 'border-status-warn/40 bg-status-warn/15 text-status-ink-warn',
  AUTO_EXECUTED: 'border-status-info/40 bg-status-info/15 text-status-ink-info',
  APPROVED: 'border-status-good/40 bg-status-good/15 text-status-ink-good',
  EXECUTED: 'border-status-good/40 bg-status-good/15 text-status-ink-good',
  OVERRIDDEN: 'border-status-info/40 bg-status-info/15 text-status-ink-info',
  REJECTED: 'border-status-critical/40 bg-status-critical/15 text-status-ink-critical',
  // Closed by events rather than a person: the load was delivered first.
  EXPIRED: 'border-line-strong bg-surface-sunken text-ink-3',
}

const TYPE_LABEL = {
  REROUTE: 'Reroute',
  MAINTENANCE: 'Maintenance',
  SPARE_PART_PURCHASE: 'Spare part',
}

const FILTERS = ['ALL', 'PENDING_APPROVAL', 'EXECUTED', 'AUTO_EXECUTED', 'REJECTED']

function StatusChip({ status }) {
  return (
    <span
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
        STATUS_STYLE[status] ?? 'border-line-strong bg-surface-sunken text-ink-2'
      }`}
    >
      {status.replace(/_/g, ' ')}
    </span>
  )
}

/**
 * What the decision layer is worth, above the ledger of what it decided.
 * Every figure comes from /api/workflows/summary; nothing is summed here.
 */
function ImpactSummary({ summary }) {
  if (!summary) return null
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricTile
        label="Loss avoided"
        value={formatInr(summary.loss_avoided_inr, { compact: true })}
        tone={summary.loss_avoided_inr > 0 ? 'good' : 'neutral'}
        sub="realised by executed reroutes"
      />
      <MetricTile
        label="Decisions automated"
        value={summary.automation_rate === null ? '—' : formatPercent(summary.automation_rate)}
        sub={`${summary.auto_executed} auto-executed · ${summary.human_resolved} by a manager`}
      />
      <MetricTile
        label="Awaiting approval"
        value={summary.pending}
        tone={summary.pending > 0 ? 'warn' : 'neutral'}
        sub={
          summary.pending > 0
            ? `${formatInr(summary.pending_impact_inr, { compact: true })} of impact held for a human`
            : 'nothing queued'
        }
      />
      <MetricTile
        label="Time to human decision"
        value={formatDuration(summary.median_seconds_to_human_decision)}
        sub="median, recommendation → approve / reject"
      />
    </div>
  )
}

export default function Workflows() {
  const fetcher = useCallback(() => api.workflows(), [])
  const { data, loading, error, refresh } = usePolling(fetcher)
  const { data: summary, refresh: refreshSummary } = usePolling(
    useCallback(() => api.workflowSummary(), []),
  )
  const [filter, setFilter] = useState('ALL')
  const [expanded, setExpanded] = useState(null)
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState(null)

  const workflows = data ?? []
  const filtered = useMemo(() => {
    if (filter === 'ALL') return workflows
    if (filter === 'EXECUTED') {
      return workflows.filter((w) => w.status === 'EXECUTED' || w.status === 'OVERRIDDEN')
    }
    return workflows.filter((w) => w.status === filter)
  }, [workflows, filter])

  const pendingCount = workflows.filter((w) => w.status === 'PENDING_APPROVAL').length

  const act = async (id, fn, message) => {
    setBusy(id)
    setNote(null)
    try {
      await fn()
      setNote(message)
      await Promise.all([refresh(), refreshSummary()])
    } catch (err) {
      setNote(err.message)
    } finally {
      setBusy(null)
    }
  }

  if (loading && !data) return <Loading label="Loading workflows…" rows={5} />

  return (
    <div className="space-y-5">
      <ErrorBanner error={error} onRetry={refresh} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink-1">Workflows</h2>
          <p className="mt-1 text-sm text-ink-3">
            Every recommendation, approval and execution, timestamped. Approvals are immutable —
            a resolved workflow is never edited, only superseded.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setFilter(option)}
              className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                filter === option
                  ? 'bg-surface-sunken text-ink-1'
                  : 'text-ink-3 hover:bg-surface-card hover:text-ink-2'
              }`}
            >
              {option === 'ALL' ? 'All' : option.replace(/_/g, ' ').toLowerCase()}
              {option === 'PENDING_APPROVAL' && pendingCount > 0 && (
                <span className="ml-1.5 rounded-full bg-status-warn px-1.5 text-[10px] font-semibold text-white">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <ImpactSummary summary={summary} />

      {note && (
        <div className="rounded-lg border border-status-info/30 bg-status-info/10 px-4 py-2.5 text-sm text-status-ink-info">
          {note}
        </div>
      )}

      <Section>
        {filtered.length === 0 ? (
          <EmptyState>No workflows match this filter.</EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Type</th>
                  <th>Recommendation</th>
                  <th>Impact</th>
                  <th>Confidence</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((w) => (
                  <Fragment key={w.id}>
                    <tr>
                      <td className="num text-ink-3">{w.id}</td>
                      <td>
                        <span className="whitespace-nowrap rounded bg-surface-sunken px-2 py-0.5 text-xs font-medium text-ink-2">
                          {TYPE_LABEL[w.workflow_type] ?? w.workflow_type.replace(/_/g, ' ').toLowerCase()}
                        </span>
                      </td>
                      {/* The width cap has to live on a block INSIDE the cell:
                          a table in auto layout ignores max-width on a <td>,
                          so this column used to expand to the full length of
                          the recommendation and shunt every other column into
                          overlapping text. */}
                      <td>
                        <div className="max-w-md whitespace-normal text-xs leading-relaxed text-ink-2">
                          {w.recommendation_text}
                        </div>
                        {w.related_shipment_id && (
                          <Link
                            to={`/shipments/${w.related_shipment_id}`}
                            className="ml-1.5 whitespace-nowrap text-status-ink-info hover:underline"
                          >
                            open shipment →
                          </Link>
                        )}
                      </td>
                      <td className="whitespace-nowrap num font-semibold text-ink-1">
                        {formatInr(w.impact_inr)}
                      </td>
                      <td className="text-xs text-ink-3">
                        {w.confidence}
                        <span className="ml-1 font-mono text-ink-3">
                          {w.confidence_score?.toFixed(2)}
                        </span>
                      </td>
                      <td>
                        <StatusChip status={w.status} />
                      </td>
                      <td className="whitespace-nowrap text-xs text-ink-3">{formatDateTime(w.created_at)}</td>
                      <td>
                        <div className="flex gap-1.5">
                          {w.requires_approval ? (
                            <>
                              <button
                                type="button"
                                disabled={busy === w.id}
                                onClick={() =>
                                  act(
                                    w.id,
                                    () => api.approveWorkflow(w.id),
                                    `Workflow #${w.id} approved and executed (simulated).`,
                                  )
                                }
                                className="btn-approve px-2.5 py-1 text-xs"
                              >
                                {busy === w.id ? '…' : 'Approve'}
                              </button>
                              <button
                                type="button"
                                disabled={busy === w.id}
                                onClick={() =>
                                  act(
                                    w.id,
                                    () => api.rejectWorkflow(w.id, 'Rejected from workflow list.'),
                                    `Workflow #${w.id} rejected — no action taken.`,
                                  )
                                }
                                className="btn-ghost px-2.5 py-1 text-xs"
                              >
                                Reject
                              </button>
                            </>
                          ) : (
                            <span className="text-[11px] text-ink-3">resolved</span>
                          )}
                          <button
                            type="button"
                            onClick={() => setExpanded(expanded === w.id ? null : w.id)}
                            className="rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:bg-surface-sunken"
                          >
                            {expanded === w.id ? 'Hide' : 'Trail'}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expanded === w.id && (
                      <tr>
                        <td colSpan={8} className="bg-surface-sunken">
                          <div className="max-w-3xl px-2 py-4">
                            <WorkflowTimeline workflow={w} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

    </div>
  )
}
