/** "2m ago" style timestamps for the review rail; dates once it's a week old. */
export function ago(value) {
  const seconds = (Date.now() - new Date(value).getTime()) / 1000
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 7 * 86400) return `${Math.floor(seconds / 86400)}d ago`
  return new Date(value).toLocaleDateString()
}

/** "16 Aug" — the history tree wants a fixed-width fact, not a shifting "2d ago". */
export function shortDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
