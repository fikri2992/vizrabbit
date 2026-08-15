<script>
const STAGE_LABEL = {
  inspector: 'Inspector, at zoom',
  pro_gate: 'Final review',
}

/**
 * What the agent flagged and then rejected. This is the evidence that it is being
 * sceptical rather than merely confident — a reviewer who only ever sees confirmed
 * defects has no way to judge whether the tool is calibrated.
 */
export default {
  name: 'DismissalLog',
  props: {
    dismissals: { type: Array, default: () => [] },
  },
  data() {
    return { open: false }
  },
  methods: {
    stage(dismissal) {
      return STAGE_LABEL[dismissal.stage] || dismissal.stage
    },
  },
}
</script>

<template>
  <section v-if="dismissals.length" class="rounded-lg border border-neutral-800">
    <button
      type="button"
      class="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-neutral-900"
      :aria-expanded="open"
      @click="open = !open"
    >
      <svg
        viewBox="0 0 24 24"
        class="size-4 shrink-0 text-neutral-500 transition"
        :class="open ? 'rotate-90' : ''"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span class="text-sm font-medium">Considered and rejected</span>
      <span class="ml-auto font-mono text-xs text-neutral-500">{{ dismissals.length }}</span>
    </button>

    <div v-if="open" class="border-t border-neutral-800 px-4 py-3">
      <p class="mb-3 text-xs text-neutral-500">
        Regions the scanner flagged that did not survive a closer look. Kept so you can judge
        whether the agent is being appropriately careful.
      </p>

      <ul class="space-y-3">
        <li v-for="dismissal in dismissals" :key="dismissal.id" class="text-sm">
          <div class="flex items-baseline gap-2">
            <span class="font-mono text-xs text-neutral-500">{{ dismissal.cells.join(', ') }}</span>
            <span class="text-xs text-neutral-600">{{ stage(dismissal) }}</span>
          </div>
          <p v-if="dismissal.hypothesis" class="mt-0.5 text-neutral-500">
            Suspected: {{ dismissal.hypothesis }}
          </p>
          <p class="mt-0.5 text-neutral-300">{{ dismissal.reason }}</p>
        </li>
      </ul>
    </div>
  </section>
</template>
