import { useState } from 'react'
import { formatTwinClock } from '../services/api.js'

/**
 * Says where the numbers came from — quietly.
 *
 * This used to render eight labelled chips in a permanent row, which meant the
 * page opened with eight pieces of metadata competing with the one thing that
 * needed a decision. Honesty does not require volume: the collapsed state is a
 * single sentence naming what is live and what is not, and the full per-stream
 * and per-waypoint detail is one click away.
 *
 * Three labels, never interchangeable:
 *   LIVE       a real external service answered (only Open-Meteo can be this)
 *   SIMULATED  produced by this application's own models
 *   PREDICTED  derived by a formula or a trained model from the two above
 */

const LABEL_STYLE = {
  LIVE: 'border-status-good/35 bg-status-good/10 text-status-ink-good',
  SIMULATED: 'border-status-warn/45 bg-status-warn/15 text-status-ink-warn',
  PREDICTED: 'border-status-info/35 bg-status-info/10 text-status-ink-info',
  MIXED: 'border-status-serious/45 bg-status-serious/15 text-status-ink-serious',
}

export function ProvenanceLabel({ label, className = '' }) {
  return (
    <span
      className={`rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${
        LABEL_STYLE[label] ?? LABEL_STYLE.SIMULATED
      } ${className}`}
    >
      {label}
    </span>
  )
}

export default function ProvenanceStrip({ provenance, environment }) {
  const [open, setOpen] = useState(false)
  if (!provenance) return null

  const { streams = [], weather, notice } = provenance
  const weatherStream = streams.find((s) => s.name === 'Weather')
  const ambient = weather?.observations?.length
    ? Math.max(...weather.observations.map((o) => o.temperature_c))
    : null

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-1 text-xs text-ink-3">
      {/* The one-line summary: everything essential, nothing more. */}
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-2 text-left hover:text-ink-2"
      >
        <ProvenanceLabel label={weatherStream?.label ?? 'SIMULATED'} />
        <span>
          {weather?.waypoints_live
            ? 'Weather from Open-Meteo'
            : 'Weather simulated (Open-Meteo unreachable)'}{' '}
          · sensors, traffic and demand simulated
        </span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>

      <span className="ml-auto flex items-center gap-4">
        {ambient != null && (
          <span className="num">
            {ambient.toFixed(0)}°C ambient
            {weather.offset_active && (
              <span className="text-status-ink-serious" title={weatherStream?.detail}>
                {' '}
                +{weather.ambient_offset_c}° injected
              </span>
            )}
          </span>
        )}
        {environment && (
          <>
            <span
              className="num"
              title="Twin time: the digital twin's clock. It runs faster than real time, so a transit plays out in minutes."
            >
              {formatTwinClock(environment.twin_time) ?? environment.sim_clock}
            </span>
            <span
              className="flex items-center gap-1.5"
              title={`The twin advances ${environment.sim_minutes_per_tick} minutes of twin time every ${environment.tick_seconds}s of real time`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  environment.physics_enabled ? 'animate-pulse bg-status-good' : 'bg-ink-3'
                }`}
              />
              {environment.physics_enabled ? 'Twin running' : 'Twin paused'}
            </span>
          </>
        )}
      </span>

      {open && (
        <div className="w-full space-y-3 rounded-card border border-line bg-surface-card p-4">
          <p className="text-xs leading-relaxed text-ink-2">{notice}</p>

          <ul className="grid gap-2 sm:grid-cols-2">
            {streams.map((stream) => (
              <li key={stream.name} className="flex gap-2">
                <ProvenanceLabel label={stream.label} className="mt-px shrink-0" />
                <span className="text-xs leading-relaxed text-ink-3">
                  <span className="font-medium text-ink-2">{stream.name}</span>
                  {' — '}
                  {stream.detail}
                </span>
              </li>
            ))}
          </ul>

          {weather?.observations?.length > 0 && (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Waypoint</th>
                    <th>Temp</th>
                    <th>Humidity</th>
                    <th>Precip</th>
                    <th>Wind</th>
                    <th>Band</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {weather.observations.map((row) => (
                    <tr key={row.city}>
                      <td className="text-ink-2">{row.city}</td>
                      <td className="num">{row.temperature_c}°C</td>
                      <td className="num text-ink-3">{row.humidity_pct}%</td>
                      <td className="num text-ink-3">{row.precipitation_mm} mm</td>
                      <td className="num text-ink-3">{row.wind_kph} kph</td>
                      <td className="text-ink-2">{row.weather_level}</td>
                      <td>
                        <ProvenanceLabel label={row.label} />
                        <span className="ml-1.5 text-[10px] text-ink-3">{row.condition}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
