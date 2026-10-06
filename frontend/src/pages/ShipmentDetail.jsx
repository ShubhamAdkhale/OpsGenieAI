import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, formatInr, formatMinutes, formatPercent } from '../services/api.js'
import { usePolling } from '../hooks/usePolling.js'
import RiskBadge from '../components/RiskBadge.jsx'
import RouteCompareCard from '../components/RouteCompareCard.jsx'
import ExplainabilityPanel from '../components/ExplainabilityPanel.jsx'
import WorkflowTimeline from '../components/WorkflowTimeline.jsx'
import {
  ErrorBanner,
  Loading,
  MeltIndexDial,
  MetricTile,
  Section,
} from '../components/ui.jsx'

/** Page 2 (§27) — the screen the demo lives on. */

export default function ShipmentDetail() {
  const { id } = useParams()
  const fetcher = useCallback(() => api.shipment(id), [id])
  const { data, loading, error, refresh } = usePolling(fetcher)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [actionNote, setActionNote] = useState(null)

  if (loading && !data) return <Loading label="Loading shipment…" rows={6} />
  if (!data) return <ErrorBanner error={error} onRetry={refresh} />

  const workflow = data.pending_reroute_workflow
  const recommendedId = data.recommended_route_evaluation?.route_id
  const currentId = data.current_route_evaluation?.route_id

  const act = async (fn, note) => {
    setBusy(true)
    setActionError(null)
    try {
      await fn()
      setActionNote(note)
      await refresh()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const approveRoute = (routeId) => {
    if (workflow) {
      const override = routeId === workflow.proposed_route_id ? null : routeId
      return act(
        () => api.approveWorkflow(workflow.id, override),
        override
          ? 'Approved with a manager override — logged as OVERRIDDEN.'
          : 'Reroute approved and executed (simulated).',
      )
    }
    // No workflow open (e.g. a low-risk shipment) — go through the direct
    // reroute endpoint, which still creates an auditable workflow record.
    return act(
      () => api.reroute(data.id, routeId),
      'Reroute executed (simulated) and logged as a workflow.',
    )
  }

  return (
    <div className="space-y-5">
      <ErrorBanner error={error} onRetry={refresh} />

      <div className="flex flex-wrap items-center gap-3">
        <Link to="/" className="text-xs text-status-ink-info hover:underline">
          ← Control Tower
        </Link>
        <span className="text-xs text-ink-3">/</span>
        <span className="font-mono text-xs text-ink-3">{data.code}</span>
      </div>

      {/* Header */}
      <Section>
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="font-mono text-2xl font-semibold text-ink-1">{data.code}</h2>
              <RiskBadge status={data.status} size="lg" pulse />
              {data.is_hero && (
                <span className="rounded border border-status-info/40 bg-status-info/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-status-ink-info">
                  demo shipment
                </span>
              )}
            </div>
            <p className="mt-2 text-sm text-ink-2">
              {data.product} · {data.category} · {data.origin_city} → {data.destination_city}
            </p>
            <p className="mt-1 text-xs text-ink-3">
              Consignment value {formatInr(data.shipment_value_inr)} · reefer{' '}
              {data.machine_id ? (
                <Link
                  to={`/machines?id=${data.machine_id}`}
                  className="font-mono text-status-ink-info hover:underline"
                >
                  {data.machine_code}
                </Link>
              ) : (
                <span className="font-mono">none</span>
              )}{' '}
              at {data.machine_health != null ? `${Math.round(data.machine_health)}% health` : '—'}{' '}
              · on {data.current_route}
            </p>
          </div>
          <MeltIndexDial value={data.melt_index} status={data.status} />
        </div>

        {/* The live thermal state. Everything below is derived from it, so it
            goes first: cargo temperature against the product's safe maximum is
            the reason the excursion counter is or is not running. */}
        <div className="mt-5 rounded-xl border border-line bg-surface-sunken p-4">
          <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-ink-3">
                Cargo temperature
                <span className="ml-1.5 rounded border border-status-warn/40 bg-status-warn/10 px-1 py-0.5 text-[8px] font-semibold text-status-ink-warn">
                  SIMULATED
                </span>
              </p>
              <p
                className={`font-mono text-3xl font-semibold num ${
                  data.cold_chain_breached ? 'text-status-ink-critical' : 'text-status-ink-info'
                }`}
              >
                {data.cargo_temperature_c?.toFixed(1)}°C
              </p>
              <p className="mt-0.5 text-[11px] text-ink-3">
                safe maximum {data.safe_transit_temp_c}°C
                {data.cold_chain_breached ? (
                  <span className="ml-1 font-semibold text-status-ink-critical">
                    — cold chain breached
                  </span>
                ) : (
                  <span className="ml-1 text-status-ink-good">— holding</span>
                )}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-ink-3">
                Ambient on lane
                <span className="ml-1.5 rounded border border-status-good/50 bg-status-good/10 px-1 py-0.5 text-[8px] font-semibold text-status-ink-good">
                  LIVE
                </span>
              </p>
              <p className="font-mono text-3xl font-semibold num text-ink-2">
                {data.ambient_temperature_c?.toFixed(1)}°C
              </p>
              <p className="mt-0.5 text-[11px] text-ink-3">Open-Meteo, when reachable</p>
            </div>
            <div className="min-w-[14rem] flex-1">
              <p className="text-[10px] uppercase tracking-wider text-ink-3">
                Heat balance
                <span className="ml-1.5 rounded border border-status-info/40 bg-status-info/10 px-1 py-0.5 text-[8px] font-semibold text-status-ink-info">
                  PREDICTED
                </span>
              </p>
              {/* Rendered verbatim from the backend's physics module — the page
                  does not re-derive the thermal model. */}
              <p className="mt-1 text-[11px] leading-relaxed text-ink-2">
                {data.thermal?.explanation}
              </p>
              {data.thermal && (
                // The raw terms are for whoever asks "show me the maths"; the
                // sentence above is what everyone else reads.
                <details className="mt-1 text-[10px] text-ink-3">
                  <summary className="cursor-pointer select-none hover:text-ink-2">
                    Model details
                  </summary>
                  <p className="num mt-1">
                    Heat ingress {data.thermal.heat_ingress_c_per_hour} °C/h · cooling{' '}
                    {data.thermal.cooling_power_c_per_hour} °C/h · net{' '}
                    {data.thermal.net_c_per_hour > 0 ? '+' : ''}
                    {data.thermal.net_c_per_hour} °C/h · ambient humidity{' '}
                    {data.thermal.humidity_pct}%
                  </p>
                </details>
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <MetricTile
            label="Spoilage probability"
            value={formatPercent(data.spoilage_probability)}
            tone={data.spoilage_probability > 0.5 ? 'bad' : 'neutral'}
          />
          <MetricTile
            label="Expected loss"
            value={formatInr(data.expected_loss_inr)}
            tone="bad"
            sub="value × probability"
          />
          <MetricTile
            label="Potential loss avoided"
            value={formatInr(data.potential_loss_avoided_inr)}
            tone="good"
            sub="if rerouted now"
          />
          <MetricTile
            label="Shelf life left"
            value={`${data.remaining_shelf_life_hours.toFixed(1)}h`}
            tone={data.remaining_shelf_life_hours < 6 ? 'bad' : 'neutral'}
            sub={`of ${data.unit_shelf_life_hours}h window`}
          />
          <MetricTile
            label="Cold-chain excursion"
            value={formatMinutes(data.minutes_outside_safe_range)}
            tone={data.minutes_outside_safe_range > 60 ? 'warn' : 'neutral'}
            sub="cumulative"
          />
          <MetricTile
            label="Loss already avoided"
            value={formatInr(data.loss_avoided_inr)}
            tone="good"
            sub="realised"
          />
        </div>
      </Section>

      {actionNote && (
        <div className="rounded-lg border border-status-good/40 bg-status-good/10 px-4 py-3 text-sm text-status-ink-good">
          {actionNote}
        </div>
      )}
      {actionError && (
        <div className="rounded-lg border border-status-critical/50 bg-status-critical/10 px-4 py-3 text-sm text-status-ink-critical">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section
          title="Why this score"
          subtitle="Generated from the stored risk assessment by fixed templates — not by a language model."
        >
          <ExplainabilityPanel explanation={data.explanation} />
        </Section>

        <Section
          title="Route comparison"
          subtitle="The optimizer minimizes expected business loss, subject to arriving inside the shelf-life window."
        >
          <RouteCompareCard
            routes={data.routes}
            currentRouteId={currentId}
            recommendedRouteId={recommendedId}
            lossAvoided={data.potential_loss_avoided_inr}
            noSafeOption={data.no_safe_option}
            onSelectRoute={approveRoute}
            disabled={busy || data.status === 'REROUTED' || data.status === 'DELIVERED'}
          />
        </Section>
      </div>

      <Section
        title="AI recommendation"
        subtitle="Approve to execute, reject to take no action, or pick a different route above to override."
      >
        <p className="text-sm leading-relaxed text-ink-2">{data.recommendation_text}</p>

        {workflow ? (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  act(
                    () => api.approveWorkflow(workflow.id),
                    'Reroute approved and executed (simulated).',
                  )
                }
                className="btn-primary"
              >
                {busy ? 'Working…' : '✓ Approve reroute'}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  act(
                    () => api.rejectWorkflow(workflow.id, 'Rejected from the shipment page.'),
                    'Recommendation rejected — no action taken.',
                  )
                }
                className="btn-danger"
              >
                ✕ Reject
              </button>
              <span className="text-xs text-ink-3">
                Impact {formatInr(workflow.impact_inr)} · {workflow.confidence} confidence
              </span>
            </div>
            <p className="mt-2 text-[11px] text-status-ink-warn">{workflow.resolution_note}</p>

            <div className="mt-5 border-t border-line pt-4">
              <p className="card-title mb-3">Workflow trail</p>
              <WorkflowTimeline workflow={workflow} />
            </div>
          </>
        ) : (
          <p className="mt-3 text-xs text-ink-3">
            {data.status === 'DELIVERED'
              ? 'This load has been delivered. Its record stays here; the lane already has its next load.'
              : data.status === 'REROUTED'
                ? 'This shipment has already been rerouted — risk mitigated.'
                : 'No approval is pending for this shipment. Use the route cards above to reroute manually.'}
          </p>
        )}

        {data.related_pending_workflows?.filter((w) => w.workflow_type !== 'REROUTE').length > 0 && (
          <div className="mt-4 rounded-lg border border-status-warn/30 bg-status-warn/[0.06] p-3">
            <p className="text-xs font-semibold text-status-ink-warn">
              Also pending for this shipment&apos;s equipment
            </p>
            <ul className="mt-1.5 space-y-1">
              {data.related_pending_workflows
                .filter((w) => w.workflow_type !== 'REROUTE')
                .map((w) => (
                  <li key={w.id} className="text-xs text-ink-2">
                    <span className="font-mono text-ink-3">#{w.id}</span>{' '}
                    {w.workflow_type.replace(/_/g, ' ')} — {w.recommendation_text}{' '}
                    <Link to="/workflows" className="text-status-ink-info hover:underline">
                      review →
                    </Link>
                  </li>
                ))}
            </ul>
          </div>
        )}
      </Section>

      {data.risk_history?.length > 1 && (
        <Section
          title="How the score evolved"
          subtitle="One point per recalculation — the audit trail behind every number on this page."
        >
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data.risk_history.map((point, index) => ({
                  step: index + 1,
                  melt_index: point.melt_index,
                }))}
                margin={{ top: 6, right: 12, bottom: 4, left: -18 }}
              >
                <XAxis dataKey="step" stroke="#87867f" fontSize={11} tickLine={false} />
                <YAxis domain={[0, 100]} stroke="#87867f" fontSize={11} tickLine={false} />
                <ReTooltip
                  contentStyle={{
                    background: '#ffffff',
                    border: '1px solid #e5e4df',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value) => [value, 'Melt Index']}
                  labelFormatter={(label) => `Recalculation #${label}`}
                />
                <Line
                  type="monotone"
                  dataKey="melt_index"
                  stroke="#eb6834"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#eb6834' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Section>
      )}

    </div>
  )
}
