<script>
import { severityRank } from '@/domain/defects'

const PIN_COLORS = {
  blocker: 'bg-red-500',
  warning: 'bg-amber-500',
  nitpick: 'bg-blue-400',
}

// Pins are positioned as percentages of the natural image size, so they stay on
// their defect at any rendered width without measuring the DOM.
export default {
  name: 'AnnotatedImage',
  props: {
    src: { type: String, required: true },
    width: { type: Number, required: true },
    height: { type: Number, required: true },
    defects: { type: Array, default: () => [] },
    selectedId: { type: String, default: '' },
  },
  emits: ['select'],
  computed: {
    pins() {
      return [...this.defects]
        .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
        .map((defect) => ({
          defect,
          left: `${(defect.circle.cx / this.width) * 100}%`,
          top: `${(defect.circle.cy / this.height) * 100}%`,
          size: `${((defect.circle.radius * 2) / this.width) * 100}%`,
          color: PIN_COLORS[defect.severity] || 'bg-neutral-400',
        }))
    },
  },
  methods: {
    isClosed(defect) {
      return ['verified_resolved', 'dismissed', 'override_approved'].includes(defect.status)
    },
  },
}
</script>

<template>
  <div class="relative select-none overflow-hidden rounded-lg bg-neutral-900">
    <img :src="src" :alt="`Reviewed asset`" class="block w-full" />

    <button
      v-for="pin in pins"
      :key="pin.defect.id"
      type="button"
      class="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 transition"
      :class="[
        selectedId === pin.defect.id
          ? 'border-white shadow-lg shadow-black/50'
          : 'border-white/70 hover:border-white',
        isClosed(pin.defect) ? 'opacity-40' : 'opacity-100',
      ]"
      :style="{ left: pin.left, top: pin.top, width: pin.size, aspectRatio: '1' }"
      :aria-label="`Pin ${pin.defect.pin}: ${pin.defect.comment}`"
      @click="$emit('select', pin.defect)"
    >
      <span
        class="absolute -left-1 -top-1 flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-xs font-bold text-black ring-2 ring-black/60"
        :class="pin.color"
      >
        {{ pin.defect.pin }}
      </span>
    </button>
  </div>
</template>
