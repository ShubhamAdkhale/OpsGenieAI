import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import RiskBadge, { riskColor } from './RiskBadge.jsx'
import { formatInr } from '../services/api.js'

/**
 * Leaflet map of shipments, coloured by risk (§28).
 *
 * §33 fallback: OpenStreetMap tiles need the internet, and the golden rule is
 * that no external service can break the demo. So we probe a single tile first
 * and fall back to a plain table if it doesn't load. The demo therefore works
 * on a dead conference wifi.
 *
 * Circle markers rather than Leaflet's default pins on purpose: the default
 * icons are separate image assets that bundlers routinely fail to resolve,
 * which would be a silent breakage on stage.
 */

const PROBE_TILE = 'https://a.tile.openstreetmap.org/5/23/13.png'
const PROBE_TIMEOUT_MS = 4000

function useTileAvailability() {
  const [available, setAvailable] = useState(null) // null = still checking

  useEffect(() => {
    let settled = false
    const finish = (value) => {
      if (!settled) {
        settled = true
        setAvailable(value)
      }
    }
    const image = new Image()
    image.onload = () => finish(true)
    image.onerror = () => finish(false)
    image.src = PROBE_TILE
    const timer = setTimeout(() => finish(false), PROBE_TIMEOUT_MS)
    return () => {
      settled = true
      clearTimeout(timer)
      image.onload = null
      image.onerror = null
    }
  }, [])

  return available
}

function TableFallback({ shipments, reason }) {
  return (
    <div>
      <div className="mb-3 rounded-lg border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-xs text-status-ink-warn">
        {reason} Showing the route table instead — every figure below is live.
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Shipment</th>
              <th>Lane</th>
              <th>Melt Index</th>
              <th>Status</th>
              <th>Expected loss</th>
            </tr>
          </thead>
          <tbody>
            {shipments.map((s) => (
              <tr key={s.id}>
                <td>
                  <Link to={`/shipments/${s.id}`} className="font-semibold text-status-ink-info hover:underline">
                    {s.code}
                  </Link>
                </td>
                <td className="text-ink-2">
                  {s.origin_city} → {s.destination_city}
                </td>
                <td className="num">{s.melt_index}</td>
                <td>
                  <RiskBadge status={s.status} size="sm" />
                </td>
                <td className="num">{formatInr(s.expected_loss_inr)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function MapView({ shipments = [], height = 380 }) {
  const tilesAvailable = useTileAvailability()

  const center = useMemo(() => {
    if (!shipments.length) return [20.5937, 78.9629] // India
    const lat = shipments.reduce((sum, s) => sum + s.origin.lat, 0) / shipments.length
    const lon = shipments.reduce((sum, s) => sum + s.origin.lon, 0) / shipments.length
    return [lat, lon]
  }, [shipments])

  if (!shipments.length) {
    return (
      <p className="py-10 text-center text-sm text-ink-3">No shipments to plot.</p>
    )
  }

  if (tilesAvailable === false) {
    return <TableFallback shipments={shipments} reason="Map tiles are unavailable offline." />
  }

  if (tilesAvailable === null) {
    return (
      <div
        className="flex items-center justify-center rounded-lg bg-surface-sunken text-sm text-ink-3"
        style={{ height }}
      >
        Checking map availability…
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg" style={{ height }}>
      <MapContainer
        center={center}
        zoom={5}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {shipments.map((s) => {
          const color = riskColor(s.status)
          const from = [s.origin.lat, s.origin.lon]
          const to = [s.destination.lat, s.destination.lon]
          return (
            <Fragment key={s.id}>
              <Polyline
                positions={[from, to]}
                pathOptions={{
                  color,
                  weight: s.is_hero ? 4 : 2,
                  opacity: s.is_hero ? 0.95 : 0.55,
                  dashArray: s.status === 'REROUTED' ? '6 6' : undefined,
                }}
              />
              <CircleMarker
                center={from}
                radius={s.is_hero ? 10 : 7}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 2 }}
              >
                <Tooltip direction="top" offset={[0, -8]}>
                  <div className="text-xs">
                    <strong>{s.code}</strong> · {s.product}
                    <br />
                    {s.origin_city} → {s.destination_city}
                    <br />
                    Melt Index <strong>{s.melt_index}</strong> ({s.status})
                    <br />
                    Expected loss {formatInr(s.expected_loss_inr)}
                  </div>
                </Tooltip>
              </CircleMarker>
              <CircleMarker
                center={to}
                radius={4}
                pathOptions={{ color, fillColor: '#f4f4f1', fillOpacity: 1, weight: 2 }}
              />
            </Fragment>
          )
        })}
      </MapContainer>
    </div>
  )
}
