/**
 * Pure defect presentation logic for the review screen — sorting, filtering, counting.
 * No I/O, no Vue. Mirrors backend/app/domain/ vocabulary exactly.
 */

export const SEVERITY_ORDER = ['blocker', 'warning', 'nitpick']
export const CATEGORIES = ['anatomy', 'physics', 'artifact', 'brand', 'memory']

export const OPEN_STATES = ['open', 'needs_human_review']
export const IN_FLIGHT_STATES = ['fix_submitted', 'agent_rechecking']
export const CLOSED_STATES = ['verified_resolved', 'dismissed', 'override_approved']

export function severityRank(severity) {
  const index = SEVERITY_ORDER.indexOf(severity)
  return index === -1 ? SEVERITY_ORDER.length : index
}

/** Blockers first, then by grid position (top-to-bottom, left-to-right) for stable pins. */
export function sortDefects(defects) {
  return [...defects].sort(
    (a, b) => severityRank(a.severity) - severityRank(b.severity) || a.pin - b.pin,
  )
}

export function filterDefects(defects, { categories = [], severities = [], statuses = [] } = {}) {
  return defects.filter(
    (defect) =>
      (categories.length === 0 || categories.includes(defect.category)) &&
      (severities.length === 0 || severities.includes(defect.severity)) &&
      (statuses.length === 0 || statuses.includes(defect.status)),
  )
}

/** A needs-human defect is a question the agent is asking, not a flag. */
export function isQuestion(defect) {
  return defect.status === 'needs_human_review'
}

/**
 * Read the code-stamped measurement back out of a brand defect's comment.
 * Mirrors backend `domain/brand.py parse_measurement` — same format, same trust
 * argument: attach_measurement writes it by code, so parsing it is safe.
 */
export function parseMeasurement(comment) {
  const match = /Measured (#[0-9a-f]{6}) against the confirmed palette: ΔE2000 (\d+(?:\.\d+)?) from the nearest brand colour (#[0-9a-f]{6})/.exec(
    comment || '',
  )
  if (!match) return null
  return { hex: match[1], deltaE: Number(match[2]), nearestHex: match[3] }
}

export function isActionable(defect) {
  return OPEN_STATES.includes(defect.status)
}

/** Drives the dashboard's per-image status chip. */
export function summarize(defects) {
  const counts = { open: 0, inFlight: 0, closed: 0, blockers: 0 }
  for (const defect of defects) {
    if (OPEN_STATES.includes(defect.status)) counts.open += 1
    else if (IN_FLIGHT_STATES.includes(defect.status)) counts.inFlight += 1
    else if (CLOSED_STATES.includes(defect.status)) counts.closed += 1
    if (defect.severity === 'blocker' && OPEN_STATES.includes(defect.status)) counts.blockers += 1
  }
  return counts
}

/** An image is publishable when nothing is left awaiting a human or the agent. */
export function isClear(defects) {
  const { open, inFlight } = summarize(defects)
  return open === 0 && inFlight === 0
}
