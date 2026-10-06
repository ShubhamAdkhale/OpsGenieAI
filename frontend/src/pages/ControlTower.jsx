import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { POLL_INTERVAL_MS, api, formatDateTime, formatInr, formatUnits } from '../services/api.js'
import { usePolling } from '../hooks/usePolling.js'
import RiskBadge from '../components/RiskBadge.jsx'
import MapView from '../components/MapView.jsx'
import AlertFeed from '../components/AlertFeed.jsx'
import PrioritySummary from '../components/PrioritySummary.jsx'
import ProvenanceStrip from '../components/ProvenanceStrip.jsx'
import RiskTrendChart from '../components/RiskTrendChart.jsx'
import PipelineStrip from '../components/PipelineStrip.jsx'
import Disclosure from '../components/Disclosure.jsx'
import { EmptyState, ErrorBanner, Loading, Section } from '../components/ui.jsx'

/**
 * The control tower.
 *
 * Reading order is the whole design. Top to bottom:
 *
 *   1. the one decision that needs making, with its money and its reason
 *   2. the pipeline that produced it, SENSE -> ACT, with a live value per stage
 *   3. where things are (map) and what just happened (alerts)
 *   4. everything else, collapsed
 *
 * The pipeline replaced the five-KPI row: it carries the same figures (loads,
 * expected loss, loss avoided, approvals) but also shows how they connect,
 * which is the product's argument. The map moved up from a closed disclosure
 * at the bottom - a first-time visitor needs to see that these are trucks on
 * real lanes before the tables mean anything.
 */

function ShipmentTable({ shipments }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Shipment</th>
            <th>Product</th>
            <th>Lane</th>
            <th>Melt</th>
            <th>Status</th>
            <th>Cargo °C</th>
            <th>Reefer</th>
            <th>Shelf left</th>
            <th>Expected loss</th>
          </tr>
        </thead>
        <tbody>
          {shipments.map((s) => (
            <tr key={s.id}>
              <td>
                <Link
                  to={`/shipments/${s.id}`}
                  className="font-mono font-semibold text-status-ink-info hover:underline"
                >
                  {s.code}
                </Link>
              </td>
              <td className="text-ink-2">{s.product}</td>
              <td className="text-ink-3">
                {s.origin_city} → {s.destination_city}
              </td>
              <td className="num text-base font-semibold text-ink-1">
                {s.melt_index}
              </td>
              <td>
                <RiskBadge status={s.status} size="sm" />
              </td>
              <td
                className={`num ${
                  s.cargo_temperature_c > s.safe_transit_temp_c
                    ? 'font-semibold text-status-ink-critical'
                    : 'text-ink-2'
                }`}
                title={`Safe maximum ${s.safe_transit_temp_c}°C`}
              >
                {s.cargo_temperature_c?.toFixed(1) ?? '—'}
              </td>
              <td className="font-mono text-xs num text-ink-2">
                {s.machine_code ?? '—'}
                {s.machine_health != null && (
                  <span className="ml-1 text-ink-3">
                    ({Math.round(s.machine_health)}%)
                  </span>
                )}
              </td>
              <td className="num text-ink-2">
                {s.remaining_shelf_life_hours.toFixed(1)}h
              </td>
              <td className="num text-status-ink-critical">
                {formatInr(s.expected_loss_inr)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DecisionLog({ workflows }) {
  if (!workflows.length) return <EmptyState>No decisions taken yet.</EmptyState>
  return (
    <ul className="space-y-2">
      {workflows.map((w) => (
        <li
          key={w.id}
          className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-1 py-2.5 text-xs last:border-b-0"
        >
          <span className="num text-ink-3">#{w.id}</span>
          <span className="font-semibold text-ink-2">
            {w.workflow_type.replace(/_/g, ' ')}
          </span>
          <span className="num text-ink-2">
            {formatInr(w.impact_inr, { compact: true })}
          </span>
          <span
            className={`flex items-center gap-1.5 text-[11px] font-medium ${
              w.status === 'PENDING_APPROVAL'
                ? 'text-status-ink-warn'
                : w.status === 'REJECTED'
                  ? 'text-status-ink-critical'
                  : 'text-status-ink-good'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                w.status === 'PENDING_APPROVAL'
                  ? 'bg-status-warn'
                  : w.status === 'REJECTED'
                    ? 'bg-status-critical'
                    : 'bg-status-good'
              }`}
              aria-hidden="true"
            />
            {w.status.replace(/_/g, ' ').toLowerCase()}
          </span>
          <span className="min-w-0 flex-1 truncate text-ink-3" title={w.trigger_reason}>
            {w.trigger_reason}
          </span>
          <span className="shrink-0 text-[10px] text-ink-3">
            {formatDateTime(w.created_at)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export default function ControlTower() {
  const fetcher = useCallback(() => api.dashboard(), [])
  const { data, loading, error, refresh } = usePolling(fetcher)
  const [busy, setBusy] = useState(false)

  const act = useCallback(
    async (fn) => {
      setBusy(true)
      try {
        await fn()
      } catch {
        /* the poll's ErrorBanner reports it; keep the button responsive */
      } finally {
        setBusy(false)
        refresh()
      }
    },
    [refresh],
  )

  const approve = useCallback(
    (id) => act(() => api.approveWorkflow(id)),
    [act],
  )
  const reject = useCallback(
    (id) => act(() => api.rejectWorkflow(id, 'Rejected from the control tower.')),
    [act],
  )

  if (loading && !data) return <Loading label="Loading control tower…" rows={5} />

  const kpis = data?.kpis ?? {}
  const shipments = data?.shipments ?? []
  const machines = data?.machines ?? []
  const alerts = data?.alerts ?? []
  const workflows = data?.workflow_activity?.recent ?? []
  const forecast = data?.forecast_summary ?? []
  const attention = machines.filter((m) => m.status !== 'HEALTHY')
  const reorder = forecast.filter((f) => f.recommended_reorder_qty > 0)

  return (
    <div className="space-y-5">
      <ErrorBanner error={error} onRetry={refresh} />

      <ProvenanceStrip provenance={data?.provenance} environment={data?.environment} />

      {/* 1. WHAT is wrong, WHAT will happen, WHY, WHAT to do, HOW MUCH. */}
      <PrioritySummary
        summary={data?.priority}
        onApprove={approve}
        onReject={reject}
        busy={busy}
      />

      {/* 2. The pipeline that produced it. */}
      <PipelineStrip data={data} />

      {/* 3. Where, and what just happened. */}
      <div className="grid gap-4 xl:grid-cols-3">
        <Section
          title="Live shipment map"
          subtitle={`${shipments.length} refrigerated loads · lanes coloured by risk status`}
          className="xl:col-span-2"
        >
          <MapView shipments={shipments} height={360} />
        </Section>

        <Section
          title="Live alerts"
          subtitle={`${alerts.length} open`}
          action={
            <span className="text-[11px] text-ink-3">
              {/* Twin time, like every other stamp on the board - not the
                  browser's refresh time, which was a fourth clock. */}
              {data?.environment?.twin_time ? `as of ${formatDateTime(data.environment.twin_time)}` : ''}
            </span>
          }
        >
          <AlertFeed alerts={alerts} maxHeight={332} />
        </Section>
      </div>

      <Disclosure
        title="Risk trend"
        badge={data?.trend?.subject_code ?? undefined}
        defaultOpen={(data?.trend?.series?.length ?? 0) > 1}
        summary="Melt Index history, from the recalculation audit trail"
      >
        <RiskTrendChart
          trend={data?.trend}
          current={data?.priority?.subject?.melt_index}
          height={240}
        />
      </Disclosure>

      {/* 4. Recent AI decisions. */}
      <Disclosure
        title="Recent AI decisions"
        badge={data?.workflow_activity?.total ?? 0}
        defaultOpen
        summary={`${data?.workflow_activity?.pending_approval ?? 0} pending · ${
          data?.workflow_activity?.auto_executed ?? 0
        } auto-executed · ${data?.workflow_activity?.executed ?? 0} executed`}
      >
        <DecisionLog workflows={workflows} />
        <Link
          to="/workflows"
          className="mt-3 inline-block text-xs text-status-ink-info hover:underline"
        >
          Full workflow history →
        </Link>
      </Disclosure>

      {/* 5. Everything else, closed. */}
      <Disclosure
        title="All shipments"
        badge={shipments.length}
        summary="Sorted by Melt Index, highest first"
      >
        {shipments.length ? (
          <ShipmentTable shipments={shipments} />
        ) : (
          <EmptyState>No shipments seeded.</EmptyState>
        )}
      </Disclosure>

      <Disclosure
        title="Equipment health"
        badge={attention.length ? `${attention.length} need attention` : 'all healthy'}
        summary={`${machines.length} units monitored`}
      >
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Unit</th>
                <th>Type</th>
                <th>Location</th>
                <th>Health</th>
                <th>Cooling</th>
                <th>Failure &lt;24h</th>
                <th>Condition risk</th>
                <th>Anomaly</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {machines.map((m) => (
                <tr key={m.id}>
                  <td className="font-mono font-semibold text-ink-2">{m.code}</td>
                  <td className="text-ink-3">{m.type_label}</td>
                  <td className="text-ink-3">{m.location}</td>
                  <td className="num text-ink-2">
                    {Math.round(m.health_score)}%
                  </td>
                  <td className="num text-ink-3">
                    {m.cooling_efficiency}%
                    <span className="ml-1 text-[10px] text-ink-3">
                      / {m.baseline_cooling_efficiency}
                    </span>
                  </td>
                  <td className={`num ${m.ml_failure_probability > 0.5 ? 'font-semibold text-status-ink-critical' : 'text-ink-2'}`}>
                    {m.ml_failure_probability == null ? '—' : `${Math.round(m.ml_failure_probability * 100)}%`}
                  </td>
                  <td className={`num ${m.failure_probability > 0.75 ? 'text-status-ink-critical' : 'text-ink-3'}`}>
                    {Math.round(m.failure_probability * 100)}%
                  </td>
                  <td className="text-xs">
                    {m.anomaly_detected ? (
                      <span className="text-status-ink-warn">detected</span>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                  <td>
                    <RiskBadge status={m.status} size="sm" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Link
          to="/machines"
          className="mt-3 inline-block text-xs text-status-ink-info hover:underline"
        >
          Predictive maintenance detail →
        </Link>
      </Disclosure>

      <Disclosure
        title="Demand forecast"
        badge={reorder.length ? `${reorder.length} reorder` : 'stocked'}
        summary="Next 7 days of predicted demand against current stock"
      >
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Predicted demand</th>
                <th>Stock now</th>
                <th>Projected</th>
                <th>Stockout risk</th>
                <th>Reorder</th>
              </tr>
            </thead>
            <tbody>
              {forecast.map((f) => (
                <tr key={f.product_name}>
                  <td className="text-ink-2">{f.product_name}</td>
                  <td className="num">{formatUnits(f.predicted_demand)}</td>
                  <td className="num text-ink-3">
                    {formatUnits(f.current_stock)}
                  </td>
                  <td
                    className={`num ${
                      f.projected_inventory < 0 ? 'text-status-ink-critical' : 'text-status-ink-good'
                    }`}
                  >
                    {formatUnits(f.projected_inventory)}
                  </td>
                  <td className="num">
                    {Math.round(f.stockout_probability * 100)}%
                  </td>
                  <td className="num text-status-ink-warn">
                    {f.recommended_reorder_qty > 0
                      ? formatUnits(f.recommended_reorder_qty)
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Link
          to="/forecast"
          className="mt-3 inline-block text-xs text-status-ink-info hover:underline"
        >
          Actual vs predicted demand →
        </Link>
      </Disclosure>

      {/* One closing note, not three. The provenance line above carries the
          live/simulated split and the page footer carries the build caveat. */}
      <p className="text-xs leading-relaxed text-ink-3">
        Every figure on this board is computed by the digital twin from the conditions it is
        simulating — none is typed in. Refreshed every{' '}
        {(POLL_INTERVAL_MS / 1000).toFixed(0)}s.
      </p>
    </div>
  )
}
