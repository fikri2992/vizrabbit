import { describe, expect, it } from 'vitest'

import {
  archiveNote,
  comparePair,
  flowNodes,
  isAgentVersion,
  groupingParam,
  leavesOf,
  liveVariants,
  openDefects,
  slotCaption,
  slotPill,
  stanceFor,
  tipOf,
  variantNeighbours,
  versionTone,
} from './slots'

const version = (overrides = {}) => ({
  image: { id: 'i1', status: 'done', version: 1, ...(overrides.image || {}) },
  uploader_name: 'Maya',
  open_defects: 0,
  original_url: '/blob/i1',
  ...overrides,
})

const variant = (ordinal, overrides = {}) => ({
  variant: ordinal,
  versions: [version()],
  approved: false,
  archived_by: null,
  approved_by_name: '',
  ...overrides,
})

const slot = (overrides = {}) => ({
  slot_id: 's1',
  name: 'Hero banner',
  state: 'in_review',
  synthetic: false,
  variants: [variant(1)],
  ...overrides,
})

describe('slotPill', () => {
  it('reads complete once a variant is approved', () => {
    expect(slotPill(slot({ state: 'complete' })).label).toBe('Complete')
  })

  it('says how many candidates are waiting to be picked', () => {
    const ready = slot({
      state: 'ready_to_pick',
      variants: [variant(1), variant(2), variant(3)],
    })
    expect(slotPill(ready).label).toBe('Ready — pick 1 of 3')
  })

  it('drops the count when only one candidate is live', () => {
    expect(slotPill(slot({ state: 'ready_to_pick' })).label).toBe('Ready to approve')
  })

  it('counts open defects while work remains', () => {
    const busy = slot({ variants: [variant(1, { versions: [version({ open_defects: 3 })] })] })
    expect(slotPill(busy).label).toBe('3 open')
  })

  it('shows the agent still working when nothing is open yet', () => {
    const scanning = slot({
      variants: [variant(1, { versions: [version({ image: { status: 'scanning' } })] })],
    })
    expect(slotPill(scanning).tone).toBe('busy')
  })
})

describe('openDefects', () => {
  it('ignores archived variants — a superseded variant is nobody’s problem', () => {
    const completed = slot({
      state: 'complete',
      variants: [
        variant(1, { archived_by: 2, versions: [version({ open_defects: 4 })] }),
        variant(2, { approved: true }),
      ],
    })
    expect(openDefects(completed)).toBe(0)
    expect(liveVariants(completed)).toHaveLength(1)
  })

  it('sums across live variants', () => {
    const busy = slot({
      variants: [
        variant(1, { versions: [version({ open_defects: 2 })] }),
        variant(2, { versions: [version({ open_defects: 3 })] }),
      ],
    })
    expect(openDefects(busy)).toBe(5)
  })

  it('counts the tip, not a superseded version', () => {
    const fixed = slot({
      variants: [
        variant(1, {
          versions: [
            version({ image: { id: 'a' }, open_defects: 9 }),
            version({ image: { id: 'b', version: 2, supersedes_id: 'a' }, open_defects: 0 }),
          ],
        }),
      ],
    })
    expect(openDefects(fixed)).toBe(0)
  })

  it('counts every live branch, not just the newest one', () => {
    const branched = slot({
      variants: [
        variant(1, {
          versions: [
            version({ image: { id: 'a' }, open_defects: 9 }),
            version({ image: { id: 'b', version: 2, supersedes_id: 'a' }, open_defects: 1 }),
            version({ image: { id: 'c', version: 2, supersedes_id: 'a' }, open_defects: 2 }),
          ],
        }),
      ],
    })
    expect(openDefects(branched)).toBe(3)
  })
})

describe('version trees', () => {
  const tree = () =>
    variant(1, {
      versions: [
        version({ image: { id: 'a', version: 1, created_at: '2026-08-14T09:00:00Z' } }),
        version({
          image: { id: 'b', version: 2, supersedes_id: 'a', created_at: '2026-08-15T09:00:00Z' },
        }),
        version({
          image: { id: 'c', version: 2, supersedes_id: 'a', created_at: '2026-08-16T09:00:00Z' },
        }),
      ],
    })

  it('leaves are the live ends of every branch', () => {
    expect(leavesOf(tree()).map((leaf) => leaf.image.id)).toEqual(['b', 'c'])
  })

  it('the tip is the newest leaf, not the last list entry by accident', () => {
    expect(tipOf(tree()).image.id).toBe('c')
  })

  it('flowNodes points each version at its parent and names sibling branches', () => {
    const nodes = flowNodes(slot({ variants: [tree()] }))
    expect(nodes.map((node) => [node.id, node.parent, node.label])).toEqual([
      ['a', null, 'v1'],
      ['b', 'a', 'v2'],
      ['c', 'a', 'v2 alt2'],
    ])
  })

  it('a fix whose parent is outside the variant reads as a root, not a lost node', () => {
    const orphan = variant(1, {
      versions: [version({ image: { id: 'b', version: 2, supersedes_id: 'gone' } })],
    })
    expect(flowNodes(slot({ variants: [orphan] }))[0].parent).toBeNull()
    expect(tipOf(orphan).image.id).toBe('b')
  })
})

describe('archiveNote', () => {
  it('is empty for a live variant', () => {
    expect(archiveNote(variant(1))).toBe('')
  })

  it('names the sibling that won, never the word rejected', () => {
    const note = archiveNote(variant(1, { archived_by: 2 }))
    expect(note).toBe('Superseded by variant 2')
    expect(note.toLowerCase()).not.toContain('reject')
  })

  it('distinguishes losing a pick from failing review', () => {
    const note = archiveNote(
      variant(1, { archived_by: 2, versions: [version({ open_defects: 1 })] }),
    )
    expect(note).toBe('Superseded by variant 2 · 1 defect left open')
  })
})

describe('versionTone', () => {
  it('marks the approved node green whatever else is true', () => {
    expect(versionTone(version({ open_defects: 2 }), { approved: true })).toBe('green')
  })

  it('is amber while defects are open and green when clean', () => {
    expect(versionTone(version({ open_defects: 2 }))).toBe('amber')
    expect(versionTone(version())).toBe('green')
  })

  it('tracks the pipeline for anything not finished', () => {
    expect(versionTone(version({ image: { status: 'scanning' } }))).toBe('busy')
    expect(versionTone(version({ image: { status: 'failed' } }))).toBe('red')
  })
})

describe('groupingParam', () => {
  it('sends nothing by default, so a plain batch behaves as it always did', () => {
    expect(groupingParam()).toBeNull()
    expect(groupingParam({ grouped: false })).toBeNull()
  })

  it('asks for one new slot when the files are grouped', () => {
    expect(groupingParam({ grouped: true })).toBe('new')
  })

  it('targets an existing slot when one is named', () => {
    expect(groupingParam({ grouped: false, slotId: 's7' })).toBe('s7')
  })
})

describe('slotCaption', () => {
  it('is empty without slot context', () => {
    expect(slotCaption(null)).toBe('')
  })

  it('states the variant and the version when either has siblings', () => {
    expect(
      slotCaption({ variant: 2, variant_count: 3, version: 2, version_count: 4, siblings: [] }),
    ).toBe('Variant 2 of 3 · v2 of 4')
  })

  it('says nothing about a lone variant on its first version', () => {
    expect(
      slotCaption({ variant: 1, variant_count: 1, version: 1, version_count: 1, siblings: [] }),
    ).toBe('')
  })
})

describe('variantNeighbours', () => {
  const siblings = [
    { variant: 1, image_id: 'a' },
    { variant: 2, image_id: 'b' },
    { variant: 3, image_id: 'c' },
  ]

  it('finds both neighbours in the middle', () => {
    const { previous, next } = variantNeighbours({ variant: 2, siblings })
    expect(previous.image_id).toBe('a')
    expect(next.image_id).toBe('c')
  })

  it('stops at the ends', () => {
    expect(variantNeighbours({ variant: 1, siblings }).previous).toBeNull()
    expect(variantNeighbours({ variant: 3, siblings }).next).toBeNull()
  })
})

describe('stanceFor', () => {
  const clean = (id, extra = {}) =>
    version({ ...extra, image: { id, version: 1, status: 'done', ...(extra.image || {}) } })

  it('is silent when nothing is pickable', () => {
    const busy = slot({
      variants: [variant(1, { versions: [clean('a', { open_defects: 2 })] })],
    })
    expect(stanceFor(busy)).toBeNull()
    expect(stanceFor(slot({ state: 'complete' }))).toBeNull()
  })

  it('prefers the fix that demonstrably worked over a merely clean sibling', () => {
    const s = slot({
      variants: [
        variant(1, {
          versions: [
            version({ image: { id: 'a', version: 1 }, open_defects: 3 }),
            clean('b', { image: { id: 'b', version: 2, supersedes_id: 'a', created_at: '2026-08-01T00:00:00Z' } }),
          ],
        }),
        variant(2, {
          versions: [clean('c', { image: { id: 'c', version: 1, created_at: '2026-08-15T00:00:00Z' } })],
        }),
      ],
    })
    const stance = stanceFor(s)
    expect(stance.imageId).toBe('b') // fixed 3 defects beats newer-but-untested
    expect(stance.facts).toContain('supersedes v1 (3 open there)')
    expect(stance.facts).toContain('1 other clean option(s)')
  })

  it('marks a recommendation that is an agent draft', () => {
    const s = slot({
      variants: [
        variant(1, {
          versions: [
            version({ image: { id: 'a', version: 1 }, open_defects: 1 }),
            clean('b', {
              image: { id: 'b', version: 2, supersedes_id: 'a', uploaded_by: 'agent:qa' },
            }),
          ],
        }),
      ],
    })
    expect(stanceFor(s).draft).toBe(true)
    expect(isAgentVersion(clean('x'))).toBe(false)
  })

  it('never recommends inside an archived variant', () => {
    const s = slot({
      variants: [
        variant(1, { approved: true, versions: [clean('a', { image: { id: 'a', approved_by: 'u1' } })] }),
        variant(2, { archived_by: 1, versions: [clean('b')] }),
      ],
    })
    // complete slot → null (approval already happened)
    expect(stanceFor(slot({ state: 'complete', variants: s.variants }))).toBeNull()
  })
})

describe('comparePair', () => {
  const node = (id, supersedes = null) =>
    version({ image: { id, version: 1, supersedes_id: supersedes } })

  it('defaults to the tips of the first two variants', () => {
    const s = slot({
      variants: [
        variant(1, { versions: [node('a1'), node('a2', 'a1')] }),
        variant(2, { versions: [node('b1')] }),
      ],
    })
    expect(comparePair(flowNodes(s))).toEqual(['a2', 'b1'])
  })

  it('compares a lone variant tip against its ancestor', () => {
    const s = slot({ variants: [variant(1, { versions: [node('a1'), node('a2', 'a1')] })] })
    expect(comparePair(flowNodes(s))).toEqual(['a1', 'a2'])
  })

  it('has nothing to compare on a single-version slot', () => {
    expect(comparePair(flowNodes(slot()))).toBeNull()
  })
})
