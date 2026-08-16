/**
 * Pure slot/variant presentation logic. No I/O, no Vue.
 * Mirrors backend/app/domain/slots.py vocabulary exactly.
 */

export const SLOT_STATES = ['in_review', 'ready_to_pick', 'complete']

/** The slot card's headline: label plus the dot colour the rest of the UI uses. */
export function slotPill(slot) {
  if (slot.state === 'complete') return { label: 'Complete', dot: '#9FE1CB', tone: 'green' }
  if (slot.state === 'ready_to_pick') {
    const live = liveVariants(slot).length
    return {
      label: live > 1 ? `Ready — pick 1 of ${live}` : 'Ready to approve',
      dot: '#9FE1CB',
      tone: 'green',
    }
  }
  const open = openDefects(slot)
  if (open) return { label: `${open} open`, dot: '#FAC775', tone: 'amber' }
  return { label: 'Reviewing…', dot: '#a3a3a8', tone: 'busy' }
}

/** Variants still in the running: everything the winner has not superseded. */
export function liveVariants(slot) {
  return slot.variants.filter((variant) => variant.archived_by === null)
}

/** Open defects that still want someone. Archived variants are nobody's problem. */
export function openDefects(slot) {
  return liveVariants(slot).reduce(
    (total, variant) =>
      total + leavesOf(variant).reduce((sum, leaf) => sum + leaf.open_defects, 0),
    0,
  )
}

/** Versions nothing has fixed yet — the live end of every branch of the tree. */
export function leavesOf(variant) {
  const superseded = new Set(
    variant.versions.map((version) => version.image.supersedes_id).filter(Boolean),
  )
  return variant.versions.filter((version) => !superseded.has(version.image.id))
}

/** The version that currently represents a variant: its newest leaf. */
export function tipOf(variant) {
  const leaves = leavesOf(variant)
  return leaves.reduce(
    (latest, leaf) => (leaf.image.created_at > latest.image.created_at ? leaf : latest),
    leaves[0] || variant.versions[variant.versions.length - 1],
  )
}

/**
 * Flatten a slot into flow-canvas nodes: every version of every variant, each
 * pointing at its parent (its superseded version, or nothing for a variant root).
 *
 * Sibling fixes of the same version share a version number, so the label
 * disambiguates them positionally: the oldest keeps `v2`, the rest read `v2 alt2`…
 */
export function flowNodes(slot) {
  const nodes = []
  for (const variant of slot.variants) {
    const ids = new Set(variant.versions.map((version) => version.image.id))
    const siblingIndex = new Map() // parent id → how many children seen so far
    for (const version of variant.versions) {
      const parent =
        version.image.supersedes_id && ids.has(version.image.supersedes_id)
          ? version.image.supersedes_id
          : null
      const seen = parent ? (siblingIndex.get(parent) || 0) + 1 : 1
      if (parent) siblingIndex.set(parent, seen)
      nodes.push({
        id: version.image.id,
        parent,
        variant,
        version,
        label: seen > 1 ? `v${version.image.version} alt${seen}` : `v${version.image.version}`,
      })
    }
  }
  return nodes
}

/**
 * Why a variant is greyed out — never the word "rejected".
 *
 * Losing a pick and failing review are different fates, and a designer reading
 * the tree deserves to know which one happened to their work.
 */
export function archiveNote(variant) {
  if (variant.archived_by === null) return ''
  const left = tipOf(variant).open_defects
  const superseded = `Superseded by variant ${variant.archived_by}`
  return left ? `${superseded} · ${left} defect${left === 1 ? '' : 's'} left open` : superseded
}

/** The node's own state, for the verdict dot on the history tree. */
export function versionTone(version, { approved = false } = {}) {
  if (approved) return 'green'
  if (version.image.status === 'failed') return 'red'
  if (version.image.status !== 'done') return 'busy'
  return version.open_defects ? 'amber' : 'green'
}

export const TONE_HEX = {
  green: '#9FE1CB',
  amber: '#FAC775',
  red: '#F09595',
  busy: '#a3a3a8',
  grey: '#5F5E5A',
}

/**
 * What the staging strip's grouping control sends.
 *
 * Grouping is offered, not asked: no selection means the pre-slot behaviour of a
 * slot per file, which is why the default is null rather than a required choice.
 */
export function groupingParam({ grouped = false, slotId = '' } = {}) {
  if (slotId) return slotId
  return grouped ? 'new' : null
}

/** A version the agent authored — drawn dashed, discardable (decision 21). */
export function isAgentVersion(version) {
  return (version.image.uploaded_by || '').startsWith('agent:')
}

/**
 * The agent's stance: which pickable version it would ship, with computed facts
 * only (decision 19 — no prose the owner cannot re-derive). Null when there is
 * nothing to recommend: no clean finished version, or the slot is complete.
 *
 * Rule: among clean, finished leaves of live variants, prefer one that fixed a
 * version which had open defects (a fix that demonstrably worked), then the
 * newest. A recommendation is never an approval.
 */
export function stanceFor(slot) {
  if (slot.state === 'complete') return null
  const byId = new Map(
    slot.variants.flatMap((variant) => variant.versions.map((v) => [v.image.id, v])),
  )
  const candidates = liveVariants(slot).flatMap((variant) =>
    leavesOf(variant)
      .filter((leaf) => leaf.image.status === 'done' && !leaf.open_defects)
      .map((leaf) => ({ leaf, variant })),
  )
  if (!candidates.length) return null

  const scored = candidates.map(({ leaf, variant }) => {
    const parent = leaf.image.supersedes_id ? byId.get(leaf.image.supersedes_id) : null
    return { leaf, variant, parent, fixed: parent ? parent.open_defects : 0 }
  })
  scored.sort(
    (a, b) => b.fixed - a.fixed || (a.leaf.image.created_at < b.leaf.image.created_at ? 1 : -1),
  )
  const pick = scored[0]

  const facts = ['0 open defects', 'review finished']
  if (pick.parent) {
    facts.push(
      `supersedes v${pick.parent.image.version}` +
        (pick.parent.open_defects
          ? ` (${pick.parent.open_defects} open there)`
          : ''),
    )
  }
  if (scored.length > 1) facts.push(`${scored.length - 1} other clean option(s)`)
  return {
    imageId: pick.leaf.image.id,
    version: pick.leaf,
    variant: pick.variant.variant,
    draft: isAgentVersion(pick.leaf),
    facts,
  }
}

/** Slot context for the review header: "variant 2 of 3 · v2". */
export function slotCaption(context) {
  if (!context) return ''
  const parts = []
  if (context.variant_count > 1) parts.push(`Variant ${context.variant} of ${context.variant_count}`)
  if (context.version_count > 1) parts.push(`v${context.version} of ${context.version_count}`)
  return parts.join(' · ')
}

/** Ordinals either side of the current variant, for prev/next navigation. */
export function variantNeighbours(context) {
  if (!context) return { previous: null, next: null }
  const index = context.siblings.findIndex((sibling) => sibling.variant === context.variant)
  return {
    previous: index > 0 ? context.siblings[index - 1] : null,
    next: index >= 0 && index < context.siblings.length - 1 ? context.siblings[index + 1] : null,
  }
}
