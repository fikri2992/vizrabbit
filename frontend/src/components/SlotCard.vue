<script>
import { liveVariants, slotPill, tipOf } from '@/domain/slots'

export default {
  name: 'SlotCard',
  props: {
    projectId: { type: String, required: true },
    slot: { type: Object, required: true },
    canUpload: { type: Boolean, default: false },
    canDelete: { type: Boolean, default: false },
  },
  emits: ['add-variant', 'delete', 'rename', 'spec'],
  data() {
    return { menuOpen: false }
  },
  computed: {
    pill() {
      return slotPill(this.slot)
    },
    /** The variant the card represents: the winner if there is one, else the first live one. */
    lead() {
      const winner = this.slot.variants.find((variant) => variant.approved)
      return winner || liveVariants(this.slot)[0] || this.slot.variants[0]
    },
    cover() {
      return tipOf(this.lead)
    },
    hasVariants() {
      return this.slot.variants.length > 1
    },
    hasHistory() {
      return this.hasVariants || this.slot.variants.some((variant) => variant.versions.length > 1)
    },
    /** Marks worth a chip. Pickable is skipped — the state pill already says it. */
    chipMarks() {
      return (this.slot.marks || []).filter((mark) => mark.kind !== 'pickable')
    },
  },
  methods: {
    onVariantFile(fileList) {
      const file = Array.from(fileList).find((entry) => entry.type.startsWith('image/'))
      if (file) this.$emit('add-variant', { slotId: this.slot.slot_id, file })
      this.menuOpen = false
    },
  },
}
</script>

<template>
  <div
    class="group relative overflow-hidden rounded-lg border border-edge bg-panel transition hover:border-edge-strong"
    @mouseleave="menuOpen = false"
  >
    <!-- The card opens the flow view; the review screen is one node further in. -->
    <RouterLink
      :to="{ name: 'slot-flow', params: { projectId, slotId: slot.slot_id } }"
      class="block"
    >
      <img
        :src="cover.original_url"
        :alt="slot.name"
        class="aspect-square w-full object-cover"
      />
      <div class="flex items-center gap-2 px-3 py-2.5">
        <span class="min-w-0 truncate text-sm text-neutral-200">{{ slot.name }}</span>
        <span
          v-if="hasVariants"
          class="shrink-0 rounded-full border border-edge-strong px-1.5 text-[10px] text-neutral-500"
        >
          {{ slot.variants.length }} variants
        </span>
        <span class="ml-auto flex shrink-0 items-center gap-1.5 text-[11px] text-neutral-400">
          <span
            class="size-1.5 rounded-full"
            :class="pill.tone === 'busy' ? 'animate-pulse' : ''"
            :style="{ background: pill.dot }"
          />
          {{ pill.label }}
        </span>
      </div>
    </RouterLink>

    <!-- Derived marks (decision 20): the agent's work and gaps, discovered in place. -->
    <div v-if="chipMarks.length" class="flex flex-wrap gap-1.5 border-t border-edge px-3 py-1.5">
      <span
        v-for="mark in chipMarks"
        :key="mark.key"
        class="rounded-full border px-1.5 py-0.5 text-[10px]"
        :class="{
          'border-warning/50 text-warning': mark.kind === 'missing',
          'border-blocker/50 text-blocker': mark.kind === 'stalled',
          'border-neutral-600 text-neutral-300': mark.kind === 'question',
        }"
        :title="mark.detail"
      >
        <template v-if="mark.kind === 'missing'">missing {{ mark.label }}</template>
        <template v-else-if="mark.kind === 'stalled'">stalled {{ mark.label }}</template>
        <template v-else>{{ mark.label }} question{{ mark.label === '1' ? '' : 's' }}</template>
      </span>
    </div>

    <!-- The full history lives in the flow view now; the card just hints there is one. -->
    <div v-if="hasHistory" class="border-t border-edge px-3 py-2">
      <RouterLink
        :to="{ name: 'slot-flow', params: { projectId, slotId: slot.slot_id } }"
        class="text-[11px] text-neutral-500 hover:text-neutral-300"
      >
        View history tree →
      </RouterLink>
    </div>

    <div v-if="canUpload || canDelete" class="absolute right-2 top-2">
      <button
        type="button"
        class="rounded-md bg-ink/80 px-2 py-0.5 text-sm text-neutral-300 opacity-0 backdrop-blur transition focus:opacity-100 group-hover:opacity-100 hover:text-white"
        aria-label="Slot actions"
        @click.stop.prevent="menuOpen = !menuOpen"
      >
        ⋯
      </button>
      <div
        v-if="menuOpen"
        class="absolute right-0 mt-1 w-44 overflow-hidden rounded-md border border-edge-strong bg-panel-2 py-1 text-sm shadow-xl"
      >
        <RouterLink
          :to="{ name: 'review', params: { projectId, imageId: cover.image.id } }"
          class="block px-3 py-1.5 text-neutral-300 hover:bg-edge hover:text-white"
        >
          Open review
        </RouterLink>
        <label
          v-if="canUpload"
          class="block cursor-pointer px-3 py-1.5 text-neutral-300 hover:bg-edge hover:text-white"
        >
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="hidden"
            @change="onVariantFile($event.target.files)"
          />
          Add variant…
        </label>
        <button
          v-if="canUpload"
          type="button"
          class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-edge hover:text-white"
          @click.stop.prevent="$emit('rename', slot); menuOpen = false"
        >
          Rename slot…
        </button>
        <button
          v-if="canUpload"
          type="button"
          class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-edge hover:text-white"
          @click.stop.prevent="$emit('spec', slot); menuOpen = false"
        >
          Set deliverables…
        </button>
        <button
          v-if="canDelete"
          type="button"
          class="block w-full px-3 py-1.5 text-left text-blocker hover:bg-edge"
          @click.stop.prevent="$emit('delete', slot); menuOpen = false"
        >
          Delete slot…
        </button>
      </div>
    </div>
  </div>
</template>
