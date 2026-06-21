/**
 * Live data client for the HiveSense fleet coordinator (uAgents REST).
 *
 * The dashboard must be HONEST about where its numbers come from, so this returns
 * a small state machine instead of a bare payload:
 *   - 'live'    : coordinator reachable AND at least one hive has a verdict
 *   - 'standby' : coordinator reachable, but no verdicts have landed yet
 *   - 'offline' : coordinator unreachable / errored  -> UI falls back to demo data
 *
 * `latency` is the round-trip in ms, surfaced in the header data-link readout.
 */
/**
 * Subscribe to live verdict pushes over Server-Sent Events (Redis Pub/Sub bridge at
 * /api/events). This is an ADDITIVE enhancement: when Redis is running, the dashboard
 * refreshes the instant a verdict lands instead of waiting for the 2s poll. If the
 * endpoint is unavailable (file-store mode returns 501), EventSource errors and we
 * simply close it - the poll keeps the dashboard fully functional on its own.
 * Returns a cleanup function.
 */
export function subscribeEvents(onEvent) {
  let es;
  try {
    es = new EventSource('/api/events');
  } catch {
    return () => {};
  }
  es.onmessage = (e) => {
    let data = null;
    try { data = JSON.parse(e.data); } catch { /* ignore keep-alives */ }
    onEvent(data);
  };
  es.onerror = () => es.close();   // no SSE backend (file mode) -> rely on polling
  return () => es.close();
}

export async function pollCoordinator() {
  const t0 = performance.now();
  try {
    const res = await fetch('/api/status', { headers: { accept: 'application/json' } });
    const latency = Math.round(performance.now() - t0);
    if (!res.ok) {
      return { state: 'offline', latency, hives: null, error: 'HTTP ' + res.status };
    }
    const data = await res.json();
    const hives = data && data.hives ? data.hives : {};
    const hasVerdicts = Object.values(hives).some(h => Array.isArray(h) && h.length > 0);
    return { state: hasVerdicts ? 'live' : 'standby', latency, hives, error: null };
  } catch (err) {
    return {
      state: 'offline',
      latency: Math.round(performance.now() - t0),
      hives: null,
      error: String(err && err.message ? err.message : err),
    };
  }
}
