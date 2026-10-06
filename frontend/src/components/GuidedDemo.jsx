import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { announceDataChanged, api, formatInr } from '../services/api.js'

/**
 * The guided demo: DEMO.md, runnable by someone who has never met the presenter.
 *
 * A judge opening the hosted link on their own gets the same five-step arc the
 * presenter would walk them through. Each step presses ONE scenario button (a
 * root cause), navigates to where the consequence shows up, and prints the
 * result as the backend returned it. The captions never state a number: every
 * figure in the "Result" line comes from the response, because the arc is a
 * simulation and its exact values move with live weather.
 */

const SEEN_KEY = 'opsgenie.tour.seen'

function readSeen() {
  try {
    return window.localStorage.getItem(SEEN_KEY) === '1'
  } catch {
    return true // storage blocked: never nag
  }
}
function writeSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, '1')
  } catch {
    /* private window - fine */
  }
}

function heroLine(response, code) {
  const hero = response?.shipments?.find((s) => s.code === code)
  if (!hero) return null
  const excursion = hero.minutes_outside_safe_range
    ? ` · ${Math.round(hero.minutes_outside_safe_range)} min outside safe range`
    : ' · no excursion'
  return `${code} is now ${hero.status} — Melt Index ${hero.melt_index}, cargo ${hero.cargo_temperature_c.toFixed(1)}°C${excursion}, expected loss ${formatInr(hero.expected_loss_inr, { compact: true })}.`
}

const STEPS = [
  {
    key: 'intro',
    title: 'A cold-chain control tower',
    body:
      'OpsGenie AI watches refrigerated shipments and the equipment carrying them, predicts spoilage before it happens, puts a rupee figure on it and recommends one action. This two-minute tour drives the live simulation one root cause at a time — no number on screen is scripted.',
    action: 'Reset & start',
    run: async ({ navigate }) => {
      await api.resetSimulation()
      navigate('/')
      return 'World reset to its baseline. Every shipment starts inside its safe envelope.'
    },
  },
  {
    key: 'traffic',
    title: 'Step 1 — A traffic incident',
    body:
      'We add 95 minutes of incident delay to one lane. That is the only thing that changes. Watch the priority card: a jam does not spoil food directly — it keeps it in a warm truck for longer.',
    action: 'Add the incident',
    run: async ({ navigate, hero }) => {
      const response = await api.triggerEvent('traffic_incident')
      navigate('/')
      return heroLine(response, hero.shipment)
    },
  },
  {
    key: 'leak',
    title: 'Step 2 — A refrigerant leak',
    body:
      'This does not set a health score. It raises the reefer\'s wear rate and lets two and a half hours of twin time pass. Efficiency falls, the sensor trace drifts, and the anomaly detector fires on a genuine trajectory.',
    action: 'Start the leak',
    run: async ({ navigate, hero, ids }) => {
      const response = await api.triggerEvent('refrigeration_degradation')
      navigate(ids.machine ? `/machines?id=${ids.machine}` : '/machines')
      const m = response?.machine
      const machine = m
        ? `${m.code}: ${Math.round(m.health_score)}% health, ${m.cooling_efficiency}% cooling efficiency${m.anomaly_detected ? ', anomaly detected' : ''}. `
        : ''
      return machine + (heroLine(response, hero.shipment) ?? '')
    },
    look: 'The machine degraded — and the shipment it carries changed risk. That is the cross-module link: maintenance is an input to operations.',
  },
  {
    key: 'heat',
    title: 'Step 3 — Heat wave and storm',
    body:
      'Ambient temperature rises 11 °C and the lane re-bands to STORM. A healthy reefer would hold; a degraded one loses the race against heat ingress. Read the Heat balance panel on the shipment page.',
    action: 'Bring the heat',
    run: async ({ navigate, hero, ids }) => {
      const response = await api.triggerEvent('weather_deterioration')
      navigate(ids.shipment ? `/shipments/${ids.shipment}` : '/')
      return heroLine(response, hero.shipment)
    },
    look: 'Excursion minutes only accrue while the cargo is genuinely above its safe maximum — they are earned by the thermal model, not assigned.',
  },
  {
    key: 'approve',
    title: 'Step 4 — The decision',
    body:
      'The optimizer compares routes on expected business loss, not travel time. The impact is above the ₹1,00,000 auto-execution ceiling, so it will not act without a manager. Approve it.',
    action: 'Approve the reroute',
    run: async ({ navigate, hero }) => {
      const before = await api.dashboard()
      const rec = before?.priority?.recommendation
      if (!rec?.workflow_id || !rec?.requires_approval) {
        navigate('/')
        return 'No reroute is waiting for approval right now — the recommendation may already have been executed.'
      }
      await api.approveWorkflow(rec.workflow_id)
      navigate('/')
      const after = await api.dashboard()
      const s = after?.shipments?.find((x) => x.code === hero.shipment)
      return `Approved and executed. ${hero.shipment} now at Melt Index ${s?.melt_index ?? '—'}; ${formatInr(after?.kpis?.loss_avoided_inr, { compact: true })} of loss avoided now shows in the Act stage of the pipeline.`
    },
  },
  {
    key: 'repair',
    title: 'Step 5 — Recovery is causal too',
    body:
      'Repair the reefer. Nobody lowers a risk score: the wear rate returns to normal and the cargo starts cooling on the next ticks. Damage already done — excursion minutes, spent shelf life — does not un-happen.',
    action: 'Repair the reefer',
    run: async ({ navigate, hero }) => {
      const response = await api.triggerEvent('maintenance_completed')
      navigate('/')
      return heroLine(response, hero.shipment)
    },
  },
  {
    key: 'done',
    title: 'That is the whole loop',
    body:
      'Sense → Predict → Quantify → Decide → Act, on one board. Explore any page, or open Demo controls in the header to press the root causes yourself.',
    action: 'Finish',
    run: async () => null,
  },
]

const TourContext = createContext(null)

export function useDemoTour() {
  return useContext(TourContext)
}

export function DemoTourProvider({ children }) {
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (!readSeen()) setOpen(true)
  }, [])

  const start = useCallback(() => {
    setIndex(0)
    setOpen(true)
  }, [])
  const close = useCallback(() => {
    writeSeen()
    setOpen(false)
  }, [])

  const value = useMemo(() => ({ open, index, setIndex, start, close }), [open, index, start, close])
  return (
    <TourContext.Provider value={value}>
      {children}
      {open && <TourPanel />}
    </TourContext.Provider>
  )
}

function TourPanel() {
  const { index, setIndex, close } = useDemoTour()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [context, setContext] = useState(null)
  // Collapsible so the panel never hides the thing a step asks you to look at.
  const [minimized, setMinimized] = useState(false)

  const step = STEPS[index]
  const last = index === STEPS.length - 1
  const done = result !== null

  // Resolve the hero shipment and machine to ids once, for deep links.
  useEffect(() => {
    let cancelled = false
    Promise.all([api.scenarios(), api.dashboard()])
      .then(([sc, dash]) => {
        if (cancelled) return
        const hero = sc?.hero ?? { shipment: 'SC-1042', machine: 'RF-204' }
        setContext({
          hero,
          ids: {
            shipment: dash?.shipments?.find((s) => s.code === hero.shipment)?.id,
            machine: dash?.machines?.find((m) => m.code === hero.machine)?.id,
          },
        })
      })
      .catch(() => !cancelled && setContext({ hero: { shipment: 'SC-1042', machine: 'RF-204' }, ids: {} }))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setResult(null)
    setError(null)
  }, [index])

  const run = async () => {
    if (last) {
      close()
      return
    }
    setBusy(true)
    setError(null)
    try {
      const line = await step.run({ navigate, ...(context ?? { hero: {}, ids: {} }) })
      setResult(line ?? '')
      announceDataChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (minimized) {
    return (
      <button
        type="button"
        onClick={() => setMinimized(false)}
        className="btn-primary fixed bottom-3 right-3 z-50 shadow-raised sm:bottom-5 sm:right-5"
      >
        Guided demo · step {index + 1} of {STEPS.length} <span aria-hidden="true">▴</span>
      </button>
    )
  }

  return (
    <aside
      role="dialog"
      aria-label="Guided demo"
      className="fixed inset-x-3 bottom-3 z-50 rounded-card border border-line-strong bg-surface-card shadow-raised sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[400px]"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Guided demo</span>
        <ol className="ml-2 flex gap-1" aria-label={`Step ${index + 1} of ${STEPS.length}`}>
          {STEPS.map((s, i) => (
            <li
              key={s.key}
              className={`h-1.5 w-5 rounded-full ${i < index ? 'bg-ink-1' : i === index ? 'bg-status-info' : 'bg-line-strong'}`}
            />
          ))}
        </ol>
        <button type="button" onClick={() => setMinimized(true)} className="ml-auto rounded px-1.5 text-lg leading-none text-ink-3 hover:text-ink-1" aria-label="Minimise guided demo" title="Minimise">
          –
        </button>
        <button type="button" onClick={close} className="rounded px-1.5 text-lg leading-none text-ink-3 hover:text-ink-1" aria-label="Close guided demo" title="Close">
          ×
        </button>
      </div>

      <div className="px-4 py-3.5">
        <h3 className="text-sm font-semibold text-ink-1">{step.title}</h3>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{step.body}</p>

        {done && result && (
          <div className="mt-3 rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2">
            <p className="field-label text-status-ink-info">Result, as the model computed it</p>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-1">{result}</p>
            {step.look && <p className="mt-1.5 text-xs leading-relaxed text-ink-3">{step.look}</p>}
          </div>
        )}
        {error && (
          <p className="mt-3 rounded-lg border border-status-critical/30 bg-status-critical/5 px-3 py-2 text-xs text-status-ink-critical">
            {error}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-line px-4 py-3">
        {index > 0 && !busy && (
          <button type="button" onClick={() => setIndex(index - 1)} className="text-xs text-ink-3 hover:text-ink-1">
            ← Back
          </button>
        )}
        <div className="ml-auto flex gap-2">
          {!done && index > 0 && !last && (
            <button type="button" onClick={() => setIndex(index + 1)} className="btn-ghost px-3 py-1.5 text-xs" disabled={busy}>
              Skip
            </button>
          )}
          {done && !last ? (
            <button type="button" onClick={() => setIndex(index + 1)} className="btn-primary">
              Next →
            </button>
          ) : (
            <button type="button" onClick={run} className="btn-primary" disabled={busy || !context}>
              {busy ? 'Running…' : step.action}
            </button>
          )}
        </div>
      </div>
    </aside>
  )
}
