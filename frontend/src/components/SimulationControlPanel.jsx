import { useCallback, useState } from 'react'
import { announceDataChanged, api } from '../services/api.js'
import { usePolling } from '../hooks/usePolling.js'

/**
 * The scenario injector.
 *
 * Each button changes ONE root cause and then lets the simulation integrate
 * forward; none of them can set a Melt Index, a spoilage probability or an
 * excursion figure. The panel shows the cause and the magnitude on the face of
 * the button precisely so that is visible rather than claimed - "incident
 * delay +95 min", not "→ Melt Index 36".
 *
 * The consequence comes back in the response, and it is whatever the model
 * made of it.
 */

const CAUSE_LABEL = {
  incident_delay_minutes: 'incident delay',
  degradation_rate_per_hour: 'wear rate',
  ambient_offset_c: 'ambient temperature',
  repair: 'repair',
}

function causeChip(scenario) {
  const name = CAUSE_LABEL[scenario.cause] ?? scenario.cause
  if (scenario.cause === 'repair') return 'restores wear rate + efficiency'
  if (scenario.cause === 'ambient_offset_c') return `${name} +${scenario.amount}°C`
  if (scenario.cause === 'degradation_rate_per_hour')
    return `${name} → ${scenario.amount} pts/h`
  return `${name} +${scenario.amount} min`
}

export default function SimulationControlPanel({ onChanged, environment, variant = 'card' }) {
  const drawer = variant === 'drawer'
  // Every page polls on its own; tell all of them, not just the parent.
  const changed = () => {
    onChanged?.()
    announceDataChanged()
  }
  const { data } = usePolling(useCallback(() => api.scenarios(), []), 0)
  const [busy, setBusy] = useState(null)
  const [fired, setFired] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const scenarios = data?.scenarios ?? []

  const run = async (scenario) => {
    setBusy(scenario.event_type)
    setError(null)
    try {
      const response = await api.triggerEvent(scenario.event_type)
      setFired((prev) =>
        prev.includes(scenario.event_type) ? prev : [...prev, scenario.event_type],
      )
      setResult(response)
      changed()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const reset = async () => {
    setBusy('reset')
    setError(null)
    try {
      await api.resetSimulation()
      setFired([])
      setResult(null)
      changed()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const step = async () => {
    setBusy('tick')
    setError(null)
    try {
      await api.tick()
      changed()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const hero = result?.shipments?.find((s) => s.code === 'SC-1042')

  return (
    <div className={drawer ? '' : 'card card-pad border-dashed border-status-warn/30'}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          {!drawer && <p className="card-title text-status-ink-warn">Scenario injector</p>}
          <p className="mt-1 text-xs leading-relaxed text-ink-3">
            There is no real IoT or traffic feed, so these buttons stand in for one. Each
            changes a single <strong className="text-ink-2">root cause</strong> and then
            advances the simulation — none of them can set a risk score. Whatever appears on
            the dashboard afterwards is what the model derived from the new conditions.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={step}
            disabled={busy !== null}
            title={
              environment
                ? `Advance ${environment.sim_minutes_per_tick} simulated minutes by hand`
                : 'Advance one tick'
            }
            className="btn-ghost"
          >
            {busy === 'tick' ? '…' : '▸ Step'}
          </button>
          <button
            type="button"
            onClick={reset}
            disabled={busy !== null}
            className="btn-ghost"
          >
            {busy === 'reset' ? 'Resetting…' : '↺ Reset'}
          </button>
        </div>
      </div>

      <div className={`mt-4 grid gap-2 ${drawer ? '' : 'sm:grid-cols-2 xl:grid-cols-4'}`}>
        {scenarios.map((scenario) => {
          const done = fired.includes(scenario.event_type)
          const repair = scenario.cause === 'repair'
          return (
            <button
              key={scenario.event_type}
              type="button"
              onClick={() => run(scenario)}
              disabled={busy !== null}
              title={scenario.description}
              className={`rounded-lg border px-3 py-2.5 text-left transition-colors ${
                done
                  ? 'border-status-good/40 bg-status-good/10'
                  : repair
                    ? 'border-status-info/30 bg-surface-sunken hover:border-status-info/60 hover:bg-line'
                    : 'border-line bg-surface-sunken hover:border-status-warn/50 hover:bg-line'
              } disabled:opacity-50`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                    done ? 'bg-status-good text-white' : 'bg-line text-ink-2'
                  }`}
                >
                  {done ? '✓' : scenario.order}
                </span>
                <span className="text-sm font-semibold leading-tight text-ink-1">
                  {busy === scenario.event_type ? 'Applying…' : scenario.label}
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">
                {scenario.description}
              </p>
              <p className="mt-1.5 text-[11px] text-ink-2">
                <span className="font-medium">Changes:</span> {causeChip(scenario)}
                <span className="text-ink-3"> · then {scenario.settle_minutes} simulated minutes pass</span>
              </p>
            </button>
          )
        })}
      </div>

      {result && (
        <div className="mt-3 rounded-lg border border-status-info/30 bg-status-info/10 px-3 py-2.5 text-xs text-status-ink-info">
          <p className="font-semibold">{result.label}</p>
          <p className="mt-1 text-[11px] text-status-ink-info">
            Changed {CAUSE_LABEL[result.cause?.field] ?? result.cause?.field} by{' '}
            {result.cause?.amount} on{' '}
            {result.cause?.applied_to}, then advanced{' '}
            {result.simulated_minutes_advanced} simulated minutes.
          </p>
          {hero && (
            <p className="num mt-1.5 text-[11px] text-ink-1">
              {hero.code}: melt {hero.melt_index} ({hero.status}) · cargo{' '}
              {hero.cargo_temperature_c}°C · {hero.minutes_outside_safe_range} min out of
              range · spoilage {Math.round(hero.spoilage_probability * 100)}%
            </p>
          )}
          {result.machine && (
            <p className="num mt-1 text-[11px] text-status-ink-info">
              {result.machine.code}: health {Math.round(result.machine.health_score)}% ·
              cooling {result.machine.cooling_efficiency}% · wear{' '}
              {result.machine.degradation_rate_per_hour} pts/h
              {result.machine.anomaly_detected && ' · anomaly detected'}
            </p>
          )}
        </div>
      )}
      {error && (
        <p className="mt-3 rounded-lg border border-status-critical/40 bg-status-critical/10 px-3 py-2 text-xs text-status-ink-critical">
          {error}
        </p>
      )}
    </div>
  )
}
