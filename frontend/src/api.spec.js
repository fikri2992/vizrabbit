import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import api from './api'

/**
 * A stand-in for the browser's EventSource, so reconnect behaviour can be driven
 * deterministically. This is not a mock of the code under test — it is the
 * environment the code runs in, which vitest's jsdom does not provide.
 */
class FakeEventSource {
  static instances = []

  constructor(url, options) {
    this.url = url
    this.options = options
    this.closed = false
    FakeEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  open() {
    this.onopen?.()
  }

  send(data) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  sendRaw(data) {
    this.onmessage?.({ data })
  }

  fail() {
    this.onerror?.(new Event('error'))
  }

  static get latest() {
    return FakeEventSource.instances.at(-1)
  }
}

describe('api.stream', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('connects with credentials so the session cookie is sent', () => {
    api.stream('/api/projects/p1/events', {})
    expect(FakeEventSource.latest.url).toBe('/api/projects/p1/events')
    expect(FakeEventSource.latest.options).toEqual({ withCredentials: true })
  })

  it('delivers parsed events', () => {
    const events = []
    api.stream('/events', { onEvent: (event) => events.push(event) })

    FakeEventSource.latest.send({ stage: 'scan_started', detail: { grid: '8x8' } })

    expect(events).toEqual([{ stage: 'scan_started', detail: { grid: '8x8' } }])
  })

  it('survives a malformed frame', () => {
    const events = []
    api.stream('/events', { onEvent: (event) => events.push(event) })

    FakeEventSource.latest.sendRaw('not json{{')
    FakeEventSource.latest.send({ stage: 'ok' })

    expect(events).toEqual([{ stage: 'ok' }])
  })

  it('reports when the connection opens', () => {
    const opened = vi.fn()
    api.stream('/events', { onOpen: opened })

    FakeEventSource.latest.open()

    expect(opened).toHaveBeenCalledOnce()
  })

  it('reconnects after the server drops the stream', () => {
    api.stream('/events', {})
    expect(FakeEventSource.instances).toHaveLength(1)

    FakeEventSource.latest.fail()
    vi.advanceTimersByTime(1000)

    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('backs off exponentially between attempts', () => {
    const delays = []
    api.stream('/events', { onReconnecting: (attempt, delay) => delays.push(delay) })

    for (let i = 0; i < 4; i += 1) {
      FakeEventSource.latest.fail()
      vi.advanceTimersByTime(60000)
    }

    expect(delays).toEqual([1000, 2000, 4000, 8000])
  })

  it('caps the backoff so a long outage still retries regularly', () => {
    const delays = []
    api.stream('/events', { onReconnecting: (attempt, delay) => delays.push(delay) })

    for (let i = 0; i < 10; i += 1) {
      FakeEventSource.latest.fail()
      vi.advanceTimersByTime(60000)
    }

    expect(Math.max(...delays)).toBe(30000)
  })

  it('resets the backoff once a connection succeeds', () => {
    const delays = []
    api.stream('/events', { onReconnecting: (attempt, delay) => delays.push(delay) })

    FakeEventSource.latest.fail()
    vi.advanceTimersByTime(1000)
    FakeEventSource.latest.fail()
    vi.advanceTimersByTime(2000)
    expect(delays).toEqual([1000, 2000])

    FakeEventSource.latest.open()
    FakeEventSource.latest.fail()
    vi.advanceTimersByTime(1000)

    expect(delays.at(-1)).toBe(1000)
  })

  it('stops reconnecting once closed', () => {
    const close = api.stream('/events', {})
    close()

    FakeEventSource.instances[0].fail()
    vi.advanceTimersByTime(60000)

    expect(FakeEventSource.instances).toHaveLength(1)
  })

  it('closes the underlying connection when closed', () => {
    const close = api.stream('/events', {})
    close()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('does not leave a pending reconnect after closing mid-backoff', () => {
    const close = api.stream('/events', {})

    FakeEventSource.latest.fail()
    close()
    vi.advanceTimersByTime(60000)

    expect(FakeEventSource.instances).toHaveLength(1)
  })
})
