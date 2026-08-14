/**
 * The single fetch/SSE wrapper. AGENTS.md: components never call this directly —
 * only Pinia actions do.
 */

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  return response.status === 204 ? null : response.json()
}

export default {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: (path) => request(path, { method: 'DELETE' }),

  /** Server-sent events — the live agent activity feed. */
  stream(path, { onEvent, onError }) {
    const source = new EventSource(path, { withCredentials: true })
    source.onmessage = (event) => onEvent(JSON.parse(event.data))
    source.onerror = (event) => onError?.(event)
    return () => source.close()
  },
}
