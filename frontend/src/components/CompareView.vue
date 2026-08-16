<script>
// Compare mode (decision 25): looking, not judging. Two ways to see the
// difference between any two versions of a slot — wipe (one frame, draggable
// divider) and side-by-side (two panes, pan/zoom locked together) — read-only,
// with each side's verdict stated and the review screen one click away.

import { comparePair } from '@/domain/slots'

export default {
  name: 'CompareView',
  props: {
    projectId: { type: String, required: true },
    nodes: { type: Array, required: true }, // flowNodes(slot)
  },
  emits: ['close'],
  data() {
    let [left, right] = comparePair(this.nodes) || [null, null]
    // Arriving from a version's review screen: that version takes the left side.
    const asked = this.$route.query.left
    if (asked && this.nodes.some((n) => n.id === asked)) {
      if (asked === right) right = left
      left = asked
    }
    return {
      leftId: left,
      rightId: right,
      wipe: 0.5, // divider position, 0..1
      wiping: false,
      zoom: 1, // side-by-side: one view state drives both panes
      pan: { x: 0, y: 0 },
      panning: false,
      panFrom: { x: 0, y: 0 },
    }
  },
  computed: {
    mode() {
      return this.$route.query.mode === 'split' ? 'split' : 'wipe'
    },
    left() {
      return this.nodes.find((n) => n.id === this.leftId) || this.nodes[0]
    },
    right() {
      return this.nodes.find((n) => n.id === this.rightId) || this.nodes[1]
    },
    ratio() {
      const { width, height } = this.left.version.image
      return width && height ? width / height : 1
    },
  },
  mounted() {
    window.addEventListener('keydown', this.onKey)
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.onKey)
  },
  methods: {
    caption(node) {
      return `var ${node.variant.variant} · ${node.label}`
    },
    verdict(node) {
      if (node.variant.approved && node.version.image.approved_by) return 'Approved'
      const open = node.version.open_defects
      return open ? `${open} open defect${open === 1 ? '' : 's'}` : 'Clean'
    },
    setMode(mode) {
      this.$router.replace({ query: { ...this.$route.query, mode } })
    },
    swapSides() {
      ;[this.leftId, this.rightId] = [this.rightId, this.leftId]
    },
    onKey(event) {
      if (event.target?.closest?.('input, textarea, select')) return
      if (event.key === 'Escape') this.$emit('close')
    },
    onWipe(event) {
      if (!this.wiping) return
      const rect = this.$refs.wipeBox.getBoundingClientRect()
      this.wipe = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    },
    onWheel(event) {
      this.zoom = Math.max(1, Math.min(6, this.zoom * Math.exp(-event.deltaY * 0.002)))
      if (this.zoom === 1) this.pan = { x: 0, y: 0 }
    },
    onPanStart(event) {
      if (event.target.closest('button, a, select')) return
      this.panning = true
      this.panFrom = { x: event.clientX - this.pan.x, y: event.clientY - this.pan.y }
    },
    onPanMove(event) {
      if (!this.panning) return
      this.pan = { x: event.clientX - this.panFrom.x, y: event.clientY - this.panFrom.y }
    },
  },
}
</script>

<template>
  <div class="fixed inset-0 z-40 flex flex-col bg-ink/97 pt-[49px] backdrop-blur">
    <!-- which two are on stage, and how they are shown -->
    <div class="flex flex-wrap items-center gap-2 border-b border-edge-strong px-4 py-2">
      <span class="text-[10px] uppercase tracking-widest text-neutral-400">Compare</span>
      <select
        v-model="leftId"
        aria-label="Left version"
        class="rounded border border-edge-strong bg-panel px-2 py-1 text-xs text-neutral-100"
      >
        <option v-for="node in nodes" :key="node.id" :value="node.id">
          {{ caption(node) }} — {{ verdict(node) }}
        </option>
      </select>
      <button
        type="button"
        class="rounded border border-edge-strong px-1.5 py-1 text-xs text-neutral-400 hover:bg-edge hover:text-neutral-100"
        title="Swap sides"
        @click="swapSides"
      >
        ⇄
      </button>
      <select
        v-model="rightId"
        aria-label="Right version"
        class="rounded border border-edge-strong bg-panel px-2 py-1 text-xs text-neutral-100"
      >
        <option v-for="node in nodes" :key="node.id" :value="node.id">
          {{ caption(node) }} — {{ verdict(node) }}
        </option>
      </select>

      <div class="ml-3 flex overflow-hidden rounded-md border border-edge-strong text-xs">
        <button
          type="button"
          class="px-2.5 py-1"
          :class="mode === 'wipe' ? 'bg-neutral-50 font-medium text-neutral-900' : 'text-neutral-300 hover:bg-edge'"
          @click="setMode('wipe')"
        >
          Wipe
        </button>
        <button
          type="button"
          class="px-2.5 py-1"
          :class="mode === 'split' ? 'bg-neutral-50 font-medium text-neutral-900' : 'text-neutral-300 hover:bg-edge'"
          @click="setMode('split')"
        >
          Side by side
        </button>
      </div>

      <button
        type="button"
        class="ml-auto rounded border border-neutral-600 px-2.5 py-1 text-xs text-neutral-200 hover:bg-edge"
        @click="$emit('close')"
      >
        ✕ Close <span class="text-neutral-500">Esc</span>
      </button>
    </div>

    <!-- wipe: one frame, the divider is the comparison -->
    <div v-if="mode === 'wipe'" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-5">
      <div
        ref="wipeBox"
        class="relative max-h-full select-none touch-none overflow-hidden rounded-xl ring-1 ring-white/15"
        :style="{ aspectRatio: ratio, maxWidth: `min(100%, 76vh * ${ratio})` }"
        @pointerdown="wiping = true; onWipe($event)"
        @pointermove="onWipe"
        @pointerup="wiping = false"
        @pointerleave="wiping = false"
      >
        <img :src="right.version.original_url" :alt="caption(right)" class="block h-full w-full" draggable="false" />
        <img
          :src="left.version.original_url"
          :alt="caption(left)"
          class="absolute inset-0 h-full w-full"
          draggable="false"
          :style="{ clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)` }"
        />
        <div
          class="absolute inset-y-0 w-0.5 cursor-ew-resize bg-white shadow-[0_0_12px_rgba(0,0,0,0.8)]"
          :style="{ left: `${wipe * 100}%` }"
        >
          <span
            class="absolute left-1/2 top-1/2 flex size-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-[10px] font-bold text-neutral-900 shadow-lg"
          >⇔</span>
        </div>
      </div>
      <div class="flex w-full max-w-3xl items-center gap-2 text-[11px]">
        <span class="font-mono text-neutral-100">{{ caption(left) }}</span>
        <span class="text-neutral-400">{{ verdict(left) }}</span>
        <RouterLink
          :to="{ name: 'review', params: { projectId, imageId: left.id } }"
          class="text-neutral-400 hover:text-neutral-100"
        >Review ↗</RouterLink>
        <span class="mx-auto text-neutral-600">drag the divider</span>
        <RouterLink
          :to="{ name: 'review', params: { projectId, imageId: right.id } }"
          class="text-neutral-400 hover:text-neutral-100"
        >Review ↗</RouterLink>
        <span class="text-neutral-400">{{ verdict(right) }}</span>
        <span class="font-mono text-neutral-100">{{ caption(right) }}</span>
      </div>
    </div>

    <!-- side by side: two panes, one shared view -->
    <div
      v-else
      class="relative flex min-h-0 flex-1 gap-2 p-4"
      @wheel.prevent="onWheel"
      @pointerdown="onPanStart"
      @pointermove="onPanMove"
      @pointerup="panning = false"
      @pointerleave="panning = false"
    >
      <figure v-for="(node, side) in [left, right]" :key="side" class="flex min-w-0 flex-1 flex-col">
        <div
          class="min-h-0 flex-1 select-none overflow-hidden rounded-xl bg-black/40 ring-1 ring-white/15"
          :class="zoom > 1 ? (panning ? 'cursor-grabbing' : 'cursor-grab') : ''"
        >
          <img
            :src="node.version.original_url"
            :alt="caption(node)"
            class="h-full w-full object-contain"
            draggable="false"
            :style="{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }"
          />
        </div>
        <figcaption class="mt-1.5 flex items-center gap-2 px-1 text-[11px]">
          <span class="font-mono text-neutral-100">{{ caption(node) }}</span>
          <span class="text-neutral-400">{{ verdict(node) }}</span>
          <span class="text-neutral-500">· {{ node.version.uploader_name || 'unknown' }}</span>
          <RouterLink
            :to="{ name: 'review', params: { projectId, imageId: node.id } }"
            class="ml-auto text-neutral-400 hover:text-neutral-100"
          >Review ↗</RouterLink>
        </figcaption>
      </figure>
      <span class="pointer-events-none absolute bottom-1.5 left-1/2 -translate-x-1/2 text-[10px] text-neutral-500">
        scroll zooms both · drag pans both · {{ Math.round(zoom * 100) }}%
      </span>
    </div>
  </div>
</template>
