import RiskBadge from './RiskBadge.jsx'
import { formatInr, formatMinutes } from '../services/api.js'

/**
 * Side-by-side route comparison (§28).
 *
 * The number that decides the recommendation is EXPECTED LOSS, not ETA — so
 * that row is emphasised, and a route that wins on rupees while losing on time
 * says so out loud.
 */

function Row({ label, children, emphasis = false }) {
  return (
    <div
      className={`flex items-center justify-between gap-3 py-1.5 ${
        emphasis ? 'border-t border-line pt-2.5 mt-1' : ''
      }`}
    >
      <span className={`text-xs ${emphasis ? 'font-semibold text-ink-2' : 'text-ink-3'}`}>
        {label}
      </span>
      <span className={emphasis ? 'text-sm font-semibold text-ink-1' : 'text-sm text-ink-2'}>
        {children}
      </span>
    </div>
  )
}

function RouteCard({ route, isRecommended, isCurrent, onSelect, actionLabel, disabled }) {
  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        isRecommended
          ? 'border-status-good/60 bg-status-good/[0.06]'
          : 'border-line bg-surface-card'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-ink-1">{route.label}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {isCurrent && (
              <span className="rounded border border-status-info/40 bg-status-info/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-status-ink-info">
                Current
              </span>
            )}
            {isRecommended && (
              <span className="rounded border border-status-good/40 bg-status-good/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-status-ink-good">
                AI recommended
              </span>
            )}
            {!route.arrives_within_shelf_life && (
              <span className="rounded border border-status-critical/40 bg-status-critical/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-status-ink-critical">
                Misses window
              </span>
            )}
          </div>
        </div>
        <RiskBadge status={route.risk_status} value={Math.round(route.melt_index)} size="sm" />
      </div>

      <div className="mt-3">
        <Row label="ETA">
          <span className="num">
            {formatMinutes(route.effective_eta_minutes)}
          </span>
          {route.delay_minutes > 0 && (
            <span className="ml-1.5 text-xs font-normal text-status-ink-critical">
              (+{formatMinutes(route.delay_minutes)} delay)
            </span>
          )}
        </Row>
        <Row label="Traffic">{route.traffic_level}</Row>
        <Row label="Weather">{route.weather_level}</Row>
        <Row label="Reefer health">
          <span className="num">{route.reefer_health}%</span>
        </Row>
        <Row label="Spoilage risk">
          <span className="num">
            {Math.round(route.spoilage_probability * 100)}%
          </span>
        </Row>
        <Row label="Expected loss" emphasis>
          <span className="num">{formatInr(route.expected_loss_inr)}</span>
        </Row>
      </div>

      {route.notes && <p className="mt-2 text-[11px] leading-relaxed text-ink-3">{route.notes}</p>}

      {onSelect && (
        <button
          type="button"
          onClick={() => onSelect(route.route_id)}
          disabled={disabled || isCurrent}
          className={isRecommended ? 'btn-primary mt-3 w-full' : 'btn-ghost mt-3 w-full'}
        >
          {isCurrent ? 'Currently selected' : actionLabel}
        </button>
      )}
    </div>
  )
}

export default function RouteCompareCard({
  routes = [],
  currentRouteId,
  recommendedRouteId,
  lossAvoided,
  noSafeOption,
  onSelectRoute,
  disabled = false,
}) {
  if (!routes.length) {
    return <p className="text-sm text-ink-3">No routes registered for this shipment.</p>
  }

  const current = routes.find((r) => r.route_id === currentRouteId)
  const recommended = routes.find((r) => r.route_id === recommendedRouteId)
  const etaTradeoff =
    current &&
    recommended &&
    recommended.route_id !== current.route_id &&
    recommended.eta_minutes > current.eta_minutes

  return (
    <div className="space-y-3">
      {noSafeOption && (
        <div className="rounded-lg border border-status-critical/40 bg-status-critical/10 px-3 py-2 text-xs text-status-ink-critical">
          No route fully satisfies the shelf-life window. The recommendation below minimizes
          damage rather than preventing it.
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {routes.map((route) => (
          <RouteCard
            key={route.route_id}
            route={route}
            isCurrent={route.route_id === currentRouteId}
            isRecommended={route.route_id === recommendedRouteId}
            onSelect={onSelectRoute}
            actionLabel={
              route.route_id === recommendedRouteId ? 'Approve this route' : 'Override to this route'
            }
            disabled={disabled}
          />
        ))}
      </div>

      {etaTradeoff && (
        <p className="text-xs text-ink-3">
          Note: the recommended route has a{' '}
          <strong className="text-ink-2">longer nominal ETA</strong> than the current one, and
          is still recommended — because the optimizer minimizes expected business loss, not
          travel time.
        </p>
      )}

      {lossAvoided > 0 && (
        <div className="rounded-lg border border-status-good/40 bg-status-good/10 px-3 py-2.5">
          <p className="text-xs uppercase tracking-wider text-status-ink-good">
            Potential loss avoided
          </p>
          <p className="text-xl font-semibold num text-status-ink-good">
            {formatInr(lossAvoided)}
          </p>
        </div>
      )}
    </div>
  )
}
