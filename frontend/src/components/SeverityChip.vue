<script>
/**
 * Direction B: severity is the only colour on the page, and it lives in a dot.
 * The chrome around it stays monochrome.
 */
const SEVERITY_DOTS = {
  blocker: '#F09595',
  warning: '#FAC775',
  nitpick: '#85B7EB',
}

const STATUS_LABELS = {
  open: 'Open',
  needs_human_review: 'Needs review',
  fix_submitted: 'Fix submitted',
  agent_rechecking: 'Re-checking',
  verified_resolved: 'Resolved',
  dismissed: 'Dismissed',
  override_approved: 'Override approved',
}

const STATUS_DOTS = {
  verified_resolved: '#9FE1CB',
  needs_human_review: '#FAC775',
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
    dot() {
      if (this.severity) return SEVERITY_DOTS[this.severity] || '#77777d'
      return STATUS_DOTS[this.status] || '#77777d'
    },
    tone() {
      if (this.severity) return { color: SEVERITY_DOTS[this.severity] || '#a3a3a8' }
      return { color: '#a3a3a8' }
    },
  },
}
</script>

<template>
  <span class="inline-flex items-center gap-1.5 text-[11px] font-medium" :style="tone">
    <span class="size-1.5 rounded-full" :style="{ background: dot }" />
    {{ label }}
  </span>
</template>
