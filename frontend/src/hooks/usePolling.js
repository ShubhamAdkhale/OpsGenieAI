import { useCallback, useEffect, useRef, useState } from 'react'
import { DATA_CHANGED_EVENT, POLL_INTERVAL_MS } from '../services/api.js'

/**
 * Re-fetch on an interval (§26).
 *
 * Websockets are a P2 item; a 3-5s poll is visually indistinguishable from
 * real-time at this demo's pacing and there is one less thing to debug.
 *
 * @param fetcher async () => data — must be stable (wrap in useCallback)
 * @param intervalMs poll period; 0 disables polling (fetch once)
 * @returns {{data, loading, error, refresh, lastUpdated}}
 */
export function usePolling(fetcher, intervalMs = POLL_INTERVAL_MS) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  // Guards against a slow in-flight response landing after unmount, and
  // against overlapping ticks if the backend is briefly slower than the
  // interval.
  const alive = useRef(true)
  const inFlight = useRef(false)

  const load = useCallback(
    async ({ silent = false } = {}) => {
      if (inFlight.current) return
      inFlight.current = true
      if (!silent) setLoading(true)
      try {
        const result = await fetcher()
        if (!alive.current) return
        setData(result)
        setError(null)
        setLastUpdated(new Date())
      } catch (err) {
        if (!alive.current) return
        // Keep the last good data on screen and show the error alongside it,
        // rather than blanking a dashboard someone is presenting from.
        setError(err)
      } finally {
        inFlight.current = false
        if (alive.current && !silent) setLoading(false)
      }
    },
    [fetcher],
  )

  useEffect(() => {
    alive.current = true
    load()
    if (!intervalMs) return () => { alive.current = false }
    const timer = setInterval(() => load({ silent: true }), intervalMs)
    // A write made elsewhere (the guided demo, the scenario panel) refreshes
    // every mounted poller at once instead of waiting out the interval.
    const onChanged = () => load({ silent: true })
    window.addEventListener(DATA_CHANGED_EVENT, onChanged)
    return () => {
      alive.current = false
      clearInterval(timer)
      window.removeEventListener(DATA_CHANGED_EVENT, onChanged)
    }
  }, [load, intervalMs])

  const refresh = useCallback(() => load({ silent: true }), [load])

  return { data, loading, error, refresh, lastUpdated }
}
