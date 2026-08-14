<script>
const SEVERITY_CLASSES = {
  blocker: 'bg-red-500/15 text-red-300 ring-red-500/40',
  warning: 'bg-amber-500/15 text-amber-300 ring-amber-500/40',
  nitpick: 'bg-blue-500/15 text-blue-300 ring-blue-500/40',
}

const STATUS_LABELS = {
  open: 'Open',
  needs_human_review: 'Needs review',
  fix_submitted: 'Fix submitted',
  agent_rechecking: 'Agent re-checking',
  verified_resolved: 'Verified resolved',
  dismissed: 'Dismissed',
  override_approved: 'Override approved',
}

export default {
  name: 'SeverityChip',
  props: {
    severity: { type: String, default: '' },
    status: { type: String, default: '' },
    category: { type: String, default: '' },
  },
  computed: {
    label() {
      if (this.status) return STATUS_LABELS[this.status] || this.status
      return this.severity || this.category
    },
    classes() {
      if (this.severity) return SEVERITY_CLASSES[this.severity] || ''
      if (this.status === 'verified_resolved') return 'bg-green-500/15 text-green-300 ring-green-500/40'
      if (this.status === 'agent_rechecking') return 'bg-violet-500/15 text-violet-300 ring-violet-500/40'
      return 'bg-neutral-700/40 text-neutral-300 ring-neutral-600/50'
    },
  },
}
</script>

<template>
  <span
    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset"
    :class="classes"
  >
    {{ label }}
  </span>
</template>
