import { useCallback, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import ControlTower from './pages/ControlTower.jsx'
import ShipmentDetail from './pages/ShipmentDetail.jsx'
import PredictiveMaintenance from './pages/PredictiveMaintenance.jsx'
import SupplyChainForecast from './pages/SupplyChainForecast.jsx'
import Workflows from './pages/Workflows.jsx'
import { DemoTourProvider, useDemoTour } from './components/GuidedDemo.jsx'
import DemoControlsDrawer from './components/DemoControlsDrawer.jsx'

const NAV = [
  { to: '/', label: 'Control tower', end: true },
  { to: '/machines', label: 'Maintenance' },
  { to: '/forecast', label: 'Forecast' },
  { to: '/workflows', label: 'Workflows' },
]

/** The product mark: a cold-chain snowflake inside a monitoring tile. */
function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect width="28" height="28" rx="7" fill="#16161a" />
      <g stroke="#ffffff" strokeWidth="1.8" strokeLinecap="round">
        <path d="M14 6.5v15M7.5 10.25l13 7.5M7.5 17.75l13-7.5" />
        <path d="M11.8 7.8 14 9.6l2.2-1.8M11.8 20.2 14 18.4l2.2 1.8" />
      </g>
      <circle cx="21.5" cy="6.5" r="3" fill="#0ca30c" stroke="#16161a" strokeWidth="1.5" />
    </svg>
  )
}

/**
 * One header row: identity, navigation, and the way into the guided demo.
 *
 * The earlier build stripped this to the bare word "OpsGenie" to keep the page
 * quiet. That was right for an operator and wrong for a first-time visitor,
 * who needs to know in one glance what the product is. The mark and a short
 * descriptor do that without competing with the data below.
 */
function Header() {
  const tour = useDemoTour()
  const [controlsOpen, setControlsOpen] = useState(false)
  const closeControls = useCallback(() => setControlsOpen(false), [])
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface-card">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-4 px-4 sm:gap-8 sm:px-5">
        <NavLink to="/" className="flex shrink-0 items-center gap-2.5">
          <Logo />
          <span className="leading-tight">
            <span className="block text-sm font-semibold tracking-tight text-ink-1">
              OpsGenie <span className="text-status-ink-info">AI</span>
            </span>
            <span className="hidden text-[11px] text-ink-3 md:block">Cold-chain control tower</span>
          </span>
        </NavLink>
        {/* Said once, prominently, instead of inside every alert: this is a
            digital twin - a simulated network the product runs on. */}
        <span
          className="hidden shrink-0 rounded-md border border-status-info/35 bg-status-info/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-status-ink-info lg:inline"
          title="Every load, reefer and sensor here is simulated by OpsGenie's digital twin. Weather is live from Open-Meteo. Actions update the twin; no external courier, ERP or work-order system is called."
        >
          Digital twin
        </span>

        <nav className="flex min-w-0 gap-1 overflow-x-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-surface-sunken font-medium text-ink-1'
                    : 'text-ink-3 hover:text-ink-1'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          onClick={() => setControlsOpen(true)}
          className="btn-ghost ml-auto shrink-0 px-3 py-1.5 text-xs"
          aria-label="Open demo controls"
          title="Scenario injector"
        >
          <span aria-hidden="true">⚙</span>
          <span className="hidden sm:inline">Demo controls</span>
        </button>
        <button
          type="button"
          onClick={tour.start}
          className="btn-primary shrink-0 px-3 py-1.5 text-xs"
          aria-label="Start the guided demo"
        >
          <span aria-hidden="true">▶</span>
          <span className="hidden sm:inline">Guided demo</span>
        </button>
      </div>
      <DemoControlsDrawer open={controlsOpen} onClose={closeControls} />
    </header>
  )
}


export default function App() {
  return (
    <DemoTourProvider>
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-5">
          <Routes>
            <Route path="/" element={<ControlTower />} />
            <Route path="/shipments/:id" element={<ShipmentDetail />} />
            <Route path="/machines" element={<PredictiveMaintenance />} />
            <Route path="/forecast" element={<SupplyChainForecast />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <footer className="mx-auto max-w-[1400px] px-4 pb-10 sm:px-5">
          <p className="text-xs leading-relaxed text-ink-3">
            Running on OpsGenie&apos;s digital twin of a cold-chain network: loads, reefers, sensor
            readings and demand history are simulated; weather is live from Open-Meteo where
            reachable. Actions update the twin — no external courier, ERP or work-order system is
            called. The Melt Index is a transparent weighted formula, not a validated measurement.
          </p>
        </footer>
      </div>
    </DemoTourProvider>
  )
}
