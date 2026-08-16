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
  return liveVariants(slot).reduce((total, variant) => total + tipOf(variant).open_defects, 0)
}

export function tipOf(variant) {
  return variant.versions[variant.versions.length - 1]
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
