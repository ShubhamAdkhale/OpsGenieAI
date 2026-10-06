import { useCallback } from 'react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, formatInr, formatUnits } from '../services/api.js'
import { usePolling } from '../hooks/usePolling.js'
import KpiCard from '../components/KpiCard.jsx'
import { ErrorBanner, Loading, Section } from '../components/ui.jsx'

/** Page 4 (§27): per-product demand/inventory chart + reorder recommendation. */

function StockoutPill({ probability }) {
  const pct = Math.round(probability * 100)
  const tone =
    pct >= 70
      ? 'border-status-critical/40 bg-status-critical/15 text-status-ink-critical'
      : pct >= 40
        ? 'border-status-warn/40 bg-status-warn/15 text-status-ink-warn'
        : 'border-status-good/40 bg-status-good/15 text-status-ink-good'
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold num ${tone}`}>
      {pct}% stockout risk
    </span>
  )
}

function ProductCard({ product, horizonDays }) {
  const shortfall = product.projected_inventory < 0

  return (
    <Section
      title={product.product_name}
      subtitle={`${product.category} · ${product.warehouse_city} warehouse`}
      action={<StockoutPill probability={product.stockout_probability} />}
    >
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-lg border border-line bg-surface-sunken p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-ink-3">
            Forecast ({horizonDays}d)
          </p>
          <p className="mt-0.5 text-lg font-semibold num text-ink-1">
            {formatUnits(product.predicted_demand)}
          </p>
          <p className="text-[10px] text-ink-3">
            last {horizonDays}d actual {formatUnits(product.historical_demand)}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface-sunken p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-ink-3">Current stock</p>
          <p className="mt-0.5 text-lg font-semibold num text-ink-2">
            {formatUnits(product.current_stock)}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface-sunken p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-ink-3">Projected</p>
          <p
            className={`mt-0.5 text-lg font-semibold num ${
              shortfall ? 'text-status-ink-critical' : 'text-status-ink-good'
            }`}
          >
            {formatUnits(product.projected_inventory)}
          </p>
          <p className="text-[10px] text-ink-3">stock − forecast</p>
        </div>
        <div className="rounded-lg border border-line bg-surface-sunken p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-ink-3">Reorder</p>
          <p
            className={`mt-0.5 text-lg font-semibold num ${
              product.recommended_reorder_qty > 0 ? 'text-status-ink-warn' : 'text-ink-3'
            }`}
          >
            {product.recommended_reorder_qty > 0
              ? formatUnits(product.recommended_reorder_qty)
              : '—'}
          </p>
          <p className="text-[10px] text-ink-3">incl. 15% safety stock</p>
        </div>
      </div>

      <div className="mt-4" style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={product.daily} margin={{ top: 6, right: 12, bottom: 4, left: -20 }}>
            <CartesianGrid stroke="#ecebe6" />
            <XAxis dataKey="label" stroke="#87867f" fontSize={10} tickLine={false} interval={2} />
            <YAxis stroke="#87867f" fontSize={11} tickLine={false} />
            <ReTooltip
              contentStyle={{
                background: '#ffffff',
                border: '1px solid #e5e4df',
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar
              dataKey="actual"
              name="Historical demand"
              fill="#2a78d6"
              radius={[2, 2, 0, 0]}
              barSize={9}
            />
            <Line
              type="monotone"
              dataKey="forecast"
              name="Forecast"
              stroke="#eb6834"
              strokeWidth={2.5}
              strokeDasharray="5 4"
              dot={{ r: 3, fill: '#eb6834' }}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-1 text-[11px] text-ink-3">
        {product.model_source === 'gradient_boosting'
          ? 'Machine-learning forecast (gradient boosting), trained per product on 90 days of simulated demand: weekday pattern, 7- and 30-day averages, trend and festival days.'
          : 'Forecast from a 7-day moving average — the low-confidence fallback used when there is too little history or the model is unavailable.'}
      </p>
    </Section>
  )
}

export default function SupplyChainForecast() {
  const forecastFetcher = useCallback(() => api.forecast(), [])
  const inventoryFetcher = useCallback(() => api.inventory(), [])
  const { data, loading, error, refresh } = usePolling(forecastFetcher)
  const { data: inventory } = usePolling(inventoryFetcher)

  if (loading && !data) return <Loading label="Loading forecast…" rows={5} />

  const products = data?.products ?? []
  const stockValue = (inventory ?? []).reduce((sum, row) => sum + row.stock_value_inr, 0)

  return (
    <div className="space-y-5">
      <ErrorBanner error={error} onRetry={refresh} />

      <div>
        <h2 className="text-lg font-semibold text-ink-1">Supply Chain Forecast</h2>
        <p className="mt-1 text-sm text-ink-3">
          Demand forecast, projected inventory and reorder recommendation per product. A
          shipment lost to spoilage shows up here as demand that still has to be met.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Horizon"
          value={`${data?.horizon_days ?? 7} days`}
          sub="recursive multi-step forecast"
        />
        <KpiCard
          label="Products at stockout risk"
          value={data?.products_at_stockout_risk ?? 0}
          tone={data?.products_at_stockout_risk > 0 ? 'warn' : 'good'}
          sub="≥ 50% probability"
        />
        <KpiCard
          label="Units to reorder"
          value={formatUnits(data?.total_recommended_reorder_units ?? 0)}
          tone="warn"
          sub="across all products"
        />
        <KpiCard
          label="Stock on hand"
          value={formatInr(stockValue, { compact: true })}
          sub={`${inventory?.length ?? 0} SKUs`}
        />
      </div>

      <Section title="Inventory position">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th>Warehouse</th>
                <th>Units in stock</th>
                <th>Unit value</th>
                <th>Stock value</th>
              </tr>
            </thead>
            <tbody>
              {(inventory ?? []).map((row) => (
                <tr key={row.product_id}>
                  <td className="text-ink-2">{row.product_name}</td>
                  <td className="text-ink-3">{row.category}</td>
                  <td className="text-ink-3">{row.warehouse_city}</td>
                  <td className="num">{formatUnits(row.current_stock)}</td>
                  <td className="num text-ink-3">
                    {formatInr(row.unit_value_inr)}
                  </td>
                  <td className="num">
                    {formatInr(row.stock_value_inr, { compact: true })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        {products.map((product) => (
          <ProductCard
            key={product.product_id}
            product={product}
            horizonDays={data?.horizon_days ?? 7}
          />
        ))}
      </div>

    </div>
  )
}
