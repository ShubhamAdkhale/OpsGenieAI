/**
 * Thin fetch wrapper (§26). No state library — pages call these directly, or
 * through the usePolling hook.
 *
 * Base URL comes from VITE_API_BASE_URL; unset, it stays relative so Vite's
 * dev proxy handles it.
 */

const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export const POLL_INTERVAL_MS = Number(import.meta.env.VITE_POLL_INTERVAL_MS ?? 4000)

/** Fired after any write so every mounted poller refreshes immediately. */
export const DATA_CHANGED_EVENT = 'opsgenie:data-changed'
export function announceDataChanged() {
  window.dispatchEvent(new Event(DATA_CHANGED_EVENT))
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}/api${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (cause) {
    // §33: a network-level failure surfaces as a banner, not a blank page.
    throw new ApiError('Backend unreachable', 0)
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* response had no JSON body — keep the generic message */
    }
    throw new ApiError(detail, response.status)
  }
  return response.json()
}

const post = (path, body) =>
  request(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const api = {
  // Reads
  dashboard: () => request('/dashboard'),
  health: () => request('/health'),
  shipments: () => request('/shipments'),
  shipment: (id) => request(`/shipments/${id}`),
  shipmentRisk: (id) => request(`/shipments/${id}/risk`),
  shipmentRoutes: (id) => request(`/shipments/${id}/routes`),
  machines: () => request('/machines'),
  machine: (id) => request(`/machines/${id}`),
  forecast: () => request('/forecast'),
  inventory: () => request('/inventory'),
  workflows: () => request('/workflows'),
  workflowSummary: () => request('/workflows/summary'),
  alerts: (limit = 40) => request(`/alerts?limit=${limit}`),
  scenarios: () => request('/simulation/scenarios'),
  simulationEvents: () => request('/simulation/events'),
  environment: () => request('/simulation/environment'),
  copilot: (q) => request(`/copilot/ask?q=${encodeURIComponent(q)}`),

  // Writes
  approveWorkflow: (id, overrideRouteId = null) =>
    post(`/workflows/${id}/approve`, { override_route_id: overrideRouteId }),
  rejectWorkflow: (id, note = '') => post(`/workflows/${id}/reject`, { note }),
  reroute: (shipmentId, routeId) =>
    post(`/shipments/${shipmentId}/reroute`, { route_id: routeId }),
  createMaintenanceWorkflow: (machineId, note = '') =>
    post(`/machines/${machineId}/maintenance-workflow`, { note }),
  triggerEvent: (eventType, targetId = null) =>
    post('/simulation/trigger-event', { event_type: eventType, target_id: targetId }),
  resetSimulation: () => post('/simulation/reset'),
  tick: () => post('/simulation/tick'),
  refreshWeather: () => post('/simulation/refresh-weather'),
  markAlertsRead: () => post('/alerts/mark-read'),
}

/** ₹ formatting: Indian grouping, no decimals — these are estimates. */
export function formatInr(value, { compact = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const amount = Number(value)
  if (compact) {
    if (Math.abs(amount) >= 1e7) return `₹${(amount / 1e7).toFixed(2)} Cr`
    if (Math.abs(amount) >= 1e5) return `₹${(amount / 1e5).toFixed(2)} L`
  }
  return `₹${amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

/** Unit counts with Indian digit grouping: 12267 -> 12,267. */
export function formatUnits(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Math.round(Number(value)).toLocaleString('en-IN')
}

export function formatPercent(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return '—'
  const total = Math.round(Number(minutes))
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return hours > 0 ? `${hours}h ${rest}m` : `${rest}m`
}

/**
 * Time until cooling efficiency reaches the floor. The backend caps the
 * estimate at 30 days, beyond which a straight-line extrapolation of a
 * near-flat trend means nothing, and sends null when there is no decline.
 */
export function formatRunway(hours) {
  if (hours === null || hours === undefined) return 'stable'
  if (hours <= 0) return 'at floor now'
  if (hours >= 720) return '> 30 days'
  if (hours >= 48) return `${Math.round(hours / 24)} days`
  return `${Math.round(hours)}h`
}

/** A short human duration: 42s, 3m, 1h 5m. */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.round(Number(seconds))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}

/**
 * Every timestamp is shown in IST, whatever the viewer's machine is set to.
 * The network is in India, and twin time is defined in IST - rendering it in
 * the browser's zone would put a judge abroad on a different clock from the
 * header.
 */
export const TIME_ZONE = 'Asia/Kolkata'

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIME_ZONE,
  })
}

/** The twin's clock for the header: "Thu 24 Sep · 06:42 IST". */
export function formatTwinClock(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const day = date.toLocaleDateString('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: TIME_ZONE,
  })
  const time = date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIME_ZONE,
  })
  return `${day} · ${time} IST`
}
