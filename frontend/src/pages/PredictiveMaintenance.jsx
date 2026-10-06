import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Line, LineChart, ResponsiveContainer, Tooltip as ReTooltip, XAxis, YAxis } from 'recharts'
import { api, formatDateTime, formatPercent, formatRunway } from '../services/api.js'
import { usePolling } from '../hooks/usePolling.js'
import RiskBadge from '../components/RiskBadge.jsx'
import MachineHealthCard from '../components/MachineHealthCard.jsx'
import { EmptyState, ErrorBanner, Loading, MetricTile, Section } from '../components/ui.jsx'

/** Page 3 (§27): machine list + detail with sensor trend charts. */

// `rising` says which direction is bad, so the change label can be coloured
// by meaning rather than by sign.
const SENSOR_SERIES = [
  { key: 'cooling_efficiency', label: 'Cooling efficiency', unit: '%', rising: false },
  { key: 'temperature', label: 'Unit temperature', unit: '°C', rising: true },
  { key: 'vibration', label: 'Vibration', unit: 'mm/s', rising: true },
  { key: 'current', label: 'Current draw', unit: 'A', rising: true },
  { key: 'pressure', label: 'Pressure', unit: 'bar', rising: null },
  { key: 'humidity', label: 'Ambient humidity', unit: '%', rising: null },
]

/**
 * Small multiples, one sensor per chart, each on its own scale.
 *
 * These used to share one axis, so cooling efficiency (~50-95) flattened
 * vibration (~2-8) and current into lines that looked perfectly still even
 * while the anomaly detector was firing on them. A drift is only visible on a
 * scale fitted to that sensor.
 */
function SensorSparkChart({ series, rows }) {
  const values = rows.map((r) => r[series.key]).filter((v) => v !== null && v !== undefined)
  if (!values.length) return null
  const first = values[0]
  const latest = values[values.length - 1]
  const change = latest - first
  const worse = series.rising === null ? null : series.rising ? change > 0 : change < 0
  const significant = Math.abs(change) > Math.max(Math.abs(first) * 0.05, 0.05)
  const changeTone =
    !significant || worse === null ? 'text-ink-3' : worse ? 'text-status-ink-critical' : 'text-status-ink-good'
  const digits = Math.abs(latest) < 10 ? 2 : 1

  return (
    <div className="panel">
      <div className="flex items-baseline justify-between gap-2">
        <p className="field-label">{series.label}</p>
        <p className={`num text-[11px] ${changeTone}`}>
          {change >= 0 ? '+' : ''}
          {change.toFixed(digits)} {series.unit}
        </p>
      </div>
      <p className="num mt-0.5 text-lg font-semibold text-ink-1">
        {latest.toFixed(digits)}
        <span className="ml-1 text-xs font-normal text-ink-3">{series.unit}</span>
      </p>
      <div style={{ height: 70 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
            <YAxis hide domain={['auto', 'auto']} />
            <XAxis dataKey="index" hide />
            <ReTooltip
              contentStyle={{ background: '#ffffff', border: '1px solid #e5e4df', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(label) => `Reading #${label}`}
              formatter={(value) => [`${Number(value).toFixed(digits)} ${series.unit}`, series.label]}
            />
            <Line
              type="monotone"
              dataKey={series.key}
              stroke="#2a78d6"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function SensorChart({ readings }) {
  const rows = readings.map((r, index) => ({ index: index + 1, ...r }))
  return (
    <div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SENSOR_SERIES.map((series) => (
          <SensorSparkChart key={series.key} series={series} rows={rows} />
        ))}
      </div>
      <p className="mt-2 text-[11px] text-ink-3">
        Last {rows.length} readings, oldest to newest; change is across that window. Simulated
        sensor stream, generated from the unit's modelled wear. No outlier is injected: the
        anomaly detector is catching a genuine drift.
      </p>
    </div>
  )
}

function MachineDetail({ machineId, onWorkflowCreated }) {
  const fetcher = useCallback(() => api.machine(machineId), [machineId])
  const { data, loading, error, refresh } = usePolling(fetcher)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)

  if (loading && !data) return <Loading label="Loading machine…" rows={4} />
  if (!data) return <ErrorBanner error={error} onRetry={refresh} />

  // Two different questions: "failure < 24h" is the trend-based classifier,
  // "condition risk" is the health rule that raises workflows. When they are far
  // apart, the sub-line says which way and why rather than leave 3% beside 65%.
  const mlDisagrees =
    data.ml_failure_probability !== null &&
    data.ml_failure_probability !== undefined &&
    Math.abs(data.ml_failure_probability - data.failure_probability) > 0.4

  const createWorkflow = async () => {
    setBusy(true)
    setNote(null)
    try {
      await api.createMaintenanceWorkflow(data.id, 'Raised from the maintenance page.')
      setNote('Maintenance workflow raised — review it on the Workflows page.')
      await refresh()
      onWorkflowCreated?.()
    } catch (err) {
      setNote(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <Section>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="font-mono text-xl font-semibold text-ink-1">{data.code}</h2>
              <RiskBadge status={data.status} size="md" pulse />
            </div>
            <p className="mt-1.5 text-sm text-ink-2">
              {data.type_label} · {data.location}
            </p>
            <p className="mt-1 text-xs text-ink-3">
              Last updated {formatDateTime(data.updated_at)}
              {data.assigned_shipments?.length > 0 && (
                <>
                  {' '}
                  · carrying{' '}
                  {data.assigned_shipments.map((code, i) => (
                    <span key={code} className="font-mono text-ink-3">
                      {i > 0 && ', '}
                      {code}
                    </span>
                  ))}
                </>
              )}
            </p>
          </div>
          <button type="button" onClick={createWorkflow} disabled={busy} className="btn-ghost">
            {busy ? 'Raising…' : '+ Create maintenance workflow'}
          </button>
        </div>

        {note && (
          <p className="mt-3 rounded-lg border border-status-info/30 bg-status-info/10 px-3 py-2 text-xs text-status-ink-info">
            {note}
          </p>
        )}

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
          <MetricTile
            label="Health score"
            value={`${data.health_score}`}
            tone={data.health_score < 50 ? 'bad' : data.health_score < 80 ? 'warn' : 'good'}
          />
          <MetricTile
            label="Failure < 24h"
            value={
              data.ml_failure_probability == null ? 'n/a' : formatPercent(data.ml_failure_probability)
            }
            tone={data.ml_failure_probability > 0.5 ? 'bad' : 'neutral'}
            sub={
              !mlDisagrees
                ? 'trend-based classifier'
                : data.ml_failure_probability < data.failure_probability
                  ? 'no fast decline: worn, but not failing within a day'
                  : 'fast decline the condition score has not caught up with'
            }
          />
          <MetricTile
            label="Condition risk"
            value={formatPercent(data.failure_probability)}
            tone={data.failure_probability > 0.75 ? 'bad' : mlDisagrees ? 'warn' : 'neutral'}
            sub="from health · above 75% raises a maintenance workflow"
          />
          <MetricTile
            label="Cooling efficiency"
            value={`${data.cooling_efficiency}%`}
            sub={`baseline ${data.baseline_cooling_efficiency}%`}
            tone={
              data.baseline_cooling_efficiency - data.cooling_efficiency > 10 ? 'bad' : 'neutral'
            }
          />
          <MetricTile
            label="Wear rate"
            value={`${data.degradation_rate_per_hour}/h`}
            sub={`${data.operating_hours}h runtime · efficiency points lost per hour`}
            tone={data.degradation_rate_per_hour > 1 ? 'bad' : 'neutral'}
          />
          <MetricTile
            label="Efficiency floor in"
            value={formatRunway(data.estimated_failure_hours)}
            tone={
              data.estimated_failure_hours !== null && data.estimated_failure_hours < 12
                ? 'bad'
                : 'neutral'
            }
            sub={
              data.estimated_failure_hours === null ? 'efficiency is not declining' : 'at the current decline rate'
            }
          />
          <MetricTile
            label="Anomaly score"
            value={data.anomaly_score?.toFixed(2)}
            tone={data.anomaly_detected ? 'warn' : 'neutral'}
            sub={data.anomaly_detected ? 'anomaly detected' : 'within normal envelope'}
          />
        </div>
      </Section>

      <div className="grid gap-4 xl:grid-cols-3">
        <Section title="Sensor trends" className="xl:col-span-2">
          {data.readings?.length ? (
            <SensorChart readings={data.readings} />
          ) : (
            <EmptyState>No sensor readings recorded.</EmptyState>
          )}
        </Section>

        <Section title="Top risk factors" subtitle="Ranked by drift from nominal operation.">
          {data.insufficient_data ? (
            <div className="rounded-lg border border-line-strong bg-surface-sunken px-3 py-2.5 text-xs text-ink-2">
              Fewer than 6 readings recorded — failure prediction is skipped rather than
              guessed.
            </div>
          ) : (
            <>
              <ul className="space-y-2.5">
                {data.top_risk_factors?.length ? (
                  data.top_risk_factors.map((factor) => (
                    <li key={factor.factor}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-ink-2">
                          {factor.factor}
                        </span>
                        <span className="font-mono text-[11px] num text-ink-3">
                          {factor.severity}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-sunken">
                        <div
                          className="h-full rounded-full bg-status-warn"
                          style={{ width: `${Math.min(100, factor.severity)}%` }}
                        />
                      </div>
                      <p className="mt-1 text-[11px] leading-relaxed text-ink-3">
                        {factor.detail}
                      </p>
                    </li>
                  ))
                ) : (
                  <EmptyState>All sensors nominal.</EmptyState>
                )}
              </ul>

              {data.explanation && (
                <div className="mt-4 border-t border-line pt-3">
                  <p className="text-xs font-semibold text-ink-1">{data.explanation.headline}</p>
                  <ul className="mt-1.5 space-y-1">
                    {data.explanation.bullets.map((bullet, i) => (
                      <li key={i} className="text-[11px] leading-relaxed text-ink-3">
                        • {bullet}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {data.open_workflows?.length > 0 && (
            <div className="mt-4 rounded-lg border border-status-warn/30 bg-status-warn/[0.06] p-3">
              <p className="text-xs font-semibold text-status-ink-warn">Pending workflows</p>
              <ul className="mt-1.5 space-y-1">
                {data.open_workflows.map((w) => (
                  <li key={w.id} className="text-[11px] text-ink-2">
                    <span className="font-mono text-ink-3">#{w.id}</span>{' '}
                    {w.workflow_type.replace(/_/g, ' ')} — {w.recommendation_text}
                  </li>
                ))}
              </ul>
              <Link to="/workflows" className="mt-2 inline-block text-[11px] text-status-ink-info hover:underline">
                Approve or reject in Workflows →
              </Link>
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}

export default function PredictiveMaintenance() {
  const fetcher = useCallback(() => api.machines(), [])
  const { data, loading, error, refresh } = usePolling(fetcher)
  const [params, setParams] = useSearchParams()
  const selectedId = params.get('id')

  // Default to the unit most in need of attention.
  useEffect(() => {
    if (!selectedId && data?.length) {
      setParams({ id: String(data[0].id) }, { replace: true })
    }
  }, [selectedId, data, setParams])

  if (loading && !data) return <Loading label="Loading machines…" rows={5} />

  const machines = data ?? []

  return (
    <div className="space-y-5">
      <ErrorBanner error={error} onRetry={refresh} />

      <div>
        <h2 className="text-lg font-semibold text-ink-1">Predictive Maintenance</h2>
        <p className="mt-1 text-sm text-ink-3">
          Anomaly detection, failure-within-24h forecasts and condition risk across every
          monitored unit. A reefer whose condition risk crosses 75% raises a critical alert,
          auto-creates a maintenance
          workflow, and immediately re-scores any shipment it is carrying.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {machines.map((machine) => (
          <MachineHealthCard key={machine.id} machine={machine} compact />
        ))}
      </div>

      {selectedId && (
        <MachineDetail machineId={selectedId} onWorkflowCreated={refresh} />
      )}

    </div>
  )
}
