<script>
// The agent narrating its own work. Each pipeline stage gets a human sentence —
// this is the surface that makes the multi-agent pipeline visible rather than
// something you have to take on faith.
const STAGE_TEXT = {
  run_started: (d) => `Run started — ${d.images} image(s) queued`,
  scan_started: (d) => `Scanner reading ${d.filename} on a ${d.grid} grid`,
  scan_finished: (d) => `Scanner flagged ${d.suspects} suspect region(s) in ${d.filename}`,
  inspection_finished: (d) =>
    `Inspector confirmed ${d.confirmed}, dismissed ${d.dismissed} in ${d.filename}`,
  annotating: (d) => `Annotator drawing pin ${d.pin} at ${(d.cells || []).join(', ')}`,
  annotated: (d) =>
    d.verified
      ? `Pin ${d.pin} circle verified after ${d.iterations} check(s)`
      : `Pin ${d.pin} needs human review — circle unverified after ${d.iterations} tries`,
  pro_gate_started: () => 'Final review by the Pro model',
  pro_gate_finished: (d) => `Final review rejected ${d.rejected} finding(s)`,
  pro_gate_skipped: () => 'Final review skipped — Pro budget spent for this run',
  recheck_started: (d) => `Re-checking ${d.defects} defect(s) against ${d.filename}`,
  rechecked: (d) =>
    d.resolved
      ? `Pin ${d.pin} verified as fixed — ${d.reason}`
      : `Pin ${d.pin} still present — ${d.reason}`,
  recheck_finished: (d) => `Re-check done: ${d.closed} resolved, ${d.still_open} still open`,
  recheck_failed: (d) => `Pin ${d.pin} re-check failed, left open — ${d.error}`,
  image_finished: (d) => `${d.filename}: ${d.defects} defect(s), ${d.dismissed} dismissed`,
  image_failed: (d) => `${d.filename} failed — ${d.error}`,
  run_finished: (d) => `Run ${d.status}`,
}

const STAGE_TONE = {
  image_failed: 'text-red-400',
  recheck_failed: 'text-red-400',
  run_finished: 'text-green-400',
  image_finished: 'text-green-400',
  recheck_finished: 'text-green-400',
  pro_gate_started: 'text-neutral-200',
  pro_gate_skipped: 'text-amber-300',
}

export default {
  name: 'ActivityFeed',
  props: {
    events: { type: Array, default: () => [] },
    streaming: { type: Boolean, default: false },
  },
  methods: {
    describe(event) {
      const render = STAGE_TEXT[event.stage]
      return render ? render(event.detail || {}) : event.stage
    },
    tone(event) {
      return STAGE_TONE[event.stage] || 'text-neutral-300'
    },
    time(event) {
      return new Date(event.at).toLocaleTimeString()
    },
  },
}
</script>

<template>
  <section class="rounded-lg border border-neutral-800 bg-neutral-900/50">
    <header class="flex items-center gap-2 border-b border-neutral-800 px-4 py-2.5">
      <span
        class="size-2 rounded-full"
        :class="streaming ? 'animate-pulse bg-green-400' : 'bg-neutral-600'"
      />
      <h3 class="text-sm font-medium">Agent activity</h3>
      <span class="ml-auto text-xs text-neutral-500">{{ events.length }}</span>
    </header>

    <ul v-if="events.length" class="max-h-80 overflow-y-auto divide-y divide-neutral-800/60">
      <li v-for="(event, index) in events" :key="index" class="flex gap-3 px-4 py-2 text-sm">
        <span class="shrink-0 font-mono text-xs text-neutral-600">{{ time(event) }}</span>
        <span :class="tone(event)">{{ describe(event) }}</span>
      </li>
    </ul>

    <p v-else class="px-4 py-6 text-center text-sm text-neutral-500">
      Nothing running. Upload images to watch the agents work.
    </p>
  </section>
</template>
