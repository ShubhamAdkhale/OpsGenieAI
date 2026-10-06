import { useEffect } from 'react'
import SimulationControlPanel from './SimulationControlPanel.jsx'

/**
 * The scenario injector, as a slide-out drawer reachable from every page.
 *
 * It used to sit at the bottom of the Control Tower, which made the main board
 * read as a test harness and meant you had to scroll away from the thing you
 * were watching to press a button. It is how the demo is driven, not what an
 * operator looks at, so it now lives behind the header's "Demo controls".
 */
export default function DemoControlsDrawer({ open, onClose }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Close demo controls"
        onClick={onClose}
        className="absolute inset-0 bg-ink-1/20"
      />
      <aside
        role="dialog"
        aria-label="Demo controls"
        className="absolute inset-y-0 right-0 flex w-full max-w-[440px] flex-col border-l border-line bg-surface-card shadow-raised"
      >
        <div className="flex items-center border-b border-line px-5 py-3.5">
          <div>
            <p className="card-title text-status-ink-warn">What-if scenarios</p>
            <p className="card-subtitle">Press a root cause; watch the board derive the rest.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded px-1.5 text-lg leading-none text-ink-3 hover:text-ink-1"
            aria-label="Close demo controls"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <SimulationControlPanel variant="drawer" />
        </div>
      </aside>
    </div>
  )
}
