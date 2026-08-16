import { describe, expect, it } from 'vitest'

import {
  CLOSED_STATES,
  IN_FLIGHT_STATES,
  OPEN_STATES,
  filterDefects,
  isActionable,
  isClear,
  severityRank,
  sortDefects,
  summarize,
 isQuestion,
 parseMeasurement,
} from './defects'

const defect = (overrides = {}) => ({
  pin: 1,
  category: 'anatomy',
  severity: 'warning',
  status: 'open',
  ...overrides,
})

describe('severityRank', () => {
  it('ranks blocker above warning above nitpick', () => {
    expect(severityRank('blocker')).toBeLessThan(severityRank('warning'))
    expect(severityRank('warning')).toBeLessThan(severityRank('nitpick'))
  })

  it('sinks unknown severities to the bottom', () => {
    expect(severityRank('bogus')).toBeGreaterThan(severityRank('nitpick'))
  })
})

describe('sortDefects', () => {
  it('orders by severity, then by pin number', () => {
    const input = [
      defect({ pin: 3, severity: 'nitpick' }),
      defect({ pin: 2, severity: 'blocker' }),
      defect({ pin: 1, severity: 'warning' }),
      defect({ pin: 1, severity: 'blocker' }),
    ]
    expect(sortDefects(input).map((d) => [d.severity, d.pin])).toEqual([
      ['blocker', 1],
      ['blocker', 2],
      ['warning', 1],
      ['nitpick', 3],
    ])
  })

  it('does not mutate its input', () => {
    const input = [defect({ pin: 2, severity: 'nitpick' }), defect({ pin: 1, severity: 'blocker' })]
    const snapshot = input.map((d) => d.pin)
    sortDefects(input)
    expect(input.map((d) => d.pin)).toEqual(snapshot)
  })
})

describe('filterDefects', () => {
  const defects = [
    defect({ pin: 1, category: 'anatomy', severity: 'blocker', status: 'open' }),
    defect({ pin: 2, category: 'brand', severity: 'nitpick', status: 'verified_resolved' }),
    defect({ pin: 3, category: 'memory', severity: 'blocker', status: 'dismissed' }),
  ]

  it('returns everything when no filters are given', () => {
    expect(filterDefects(defects)).toHaveLength(3)
    expect(filterDefects(defects, {})).toHaveLength(3)
  })

  it('filters by a single axis', () => {
    expect(filterDefects(defects, { categories: ['brand'] }).map((d) => d.pin)).toEqual([2])
    expect(filterDefects(defects, { severities: ['blocker'] }).map((d) => d.pin)).toEqual([1, 3])
    expect(filterDefects(defects, { statuses: ['dismissed'] }).map((d) => d.pin)).toEqual([3])
  })

  it('ANDs multiple axes together', () => {
    expect(
      filterDefects(defects, { severities: ['blocker'], statuses: ['open'] }).map((d) => d.pin),
    ).toEqual([1])
  })

  it('returns nothing when axes contradict', () => {
    expect(filterDefects(defects, { categories: ['brand'], severities: ['blocker'] })).toEqual([])
  })
})

describe('state groupings', () => {
  it('partitions every lifecycle state exactly once', () => {
    const all = [...OPEN_STATES, ...IN_FLIGHT_STATES, ...CLOSED_STATES]
    expect(new Set(all).size).toBe(all.length)
    expect(new Set(all)).toEqual(
      new Set([
        'open',
        'needs_human_review',
        'fix_submitted',
        'agent_rechecking',
        'verified_resolved',
        'dismissed',
        'override_approved',
      ]),
    )
  })

  it('treats open and needs_human_review as actionable', () => {
    expect(isActionable(defect({ status: 'open' }))).toBe(true)
    expect(isActionable(defect({ status: 'needs_human_review' }))).toBe(true)
    expect(isActionable(defect({ status: 'agent_rechecking' }))).toBe(false)
    expect(isActionable(defect({ status: 'verified_resolved' }))).toBe(false)
  })
})

describe('summarize', () => {
  it('counts each bucket and open blockers', () => {
    const defects = [
      defect({ severity: 'blocker', status: 'open' }),
      defect({ severity: 'blocker', status: 'needs_human_review' }),
      defect({ severity: 'blocker', status: 'verified_resolved' }),
      defect({ severity: 'warning', status: 'agent_rechecking' }),
      defect({ severity: 'nitpick', status: 'dismissed' }),
    ]
    expect(summarize(defects)).toEqual({ open: 2, inFlight: 1, closed: 2, blockers: 2 })
  })

  it('does not count closed blockers as outstanding', () => {
    expect(summarize([defect({ severity: 'blocker', status: 'override_approved' })]).blockers).toBe(
      0,
    )
  })

  it('handles an empty list', () => {
    expect(summarize([])).toEqual({ open: 0, inFlight: 0, closed: 0, blockers: 0 })
  })
})

describe('isClear', () => {
  it('is clear when every defect is closed', () => {
    expect(
      isClear([defect({ status: 'verified_resolved' }), defect({ status: 'dismissed' })]),
    ).toBe(true)
  })

  it('is clear for an image with no defects', () => {
    expect(isClear([])).toBe(true)
  })

  it('is not clear while the agent is still re-checking', () => {
    expect(isClear([defect({ status: 'agent_rechecking' })])).toBe(false)
  })

  it('a question awaiting a human does not block — approving past it is an answer', () => {
    // Changed by decision 19: needs_human_review is a question, not a flag.
    expect(isClear([defect({ status: 'needs_human_review' })])).toBe(true)
  })
})

describe('questions', () => {
  it('a needs-human defect is a question, everything else is not', () => {
    expect(isQuestion({ status: 'needs_human_review' })).toBe(true)
    expect(isQuestion({ status: 'open' })).toBe(false)
  })

  it('parses the code-stamped measurement, mirroring the backend format', () => {
    const comment =
      'CTA teal looks off. Measured #3aad88 against the confirmed palette: ' +
      'ΔE2000 5.19 from the nearest brand colour #2aa47d (accent teal), which allows 3.0.'
    expect(parseMeasurement(comment)).toEqual({
      hex: '#3aad88',
      deltaE: 5.19,
      nearestHex: '#2aa47d',
    })
  })

  it('refuses prose that merely mentions a delta-E', () => {
    expect(parseMeasurement('the model thinks ΔE is big')).toBeNull()
    expect(parseMeasurement('')).toBeNull()
  })
})

describe('isClear vs questions', () => {
  it('an unanswered question never blocks the approve button', () => {
    expect(isClear([{ status: 'needs_human_review', severity: 'warning' }])).toBe(true)
    expect(isClear([{ status: 'open', severity: 'warning' }])).toBe(false)
    expect(
      isClear([
        { status: 'needs_human_review', severity: 'warning' },
        { status: 'fix_submitted', severity: 'warning' },
      ]),
    ).toBe(false)
  })
})
