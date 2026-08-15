<script>
import { severityRank } from '@/domain/defects'

const PIN_COLORS = {
  blocker: 'bg-red-500',
  warning: 'bg-amber-500',
  nitpick: 'bg-blue-400',
}
const RING_COLORS = {
  blocker: 'stroke-red-500',
  warning: 'stroke-amber-500',
  nitpick: 'stroke-blue-400',
}

const MIN_ZOOM = 1
const MAX_ZOOM = 8
const CLOSED_STATES = ['verified_resolved', 'dismissed', 'override_approved']

/**
 * The review canvas. The product's whole premise is that defects are found by
 * looking closely, so the reviewer has to be able to look closely too — a static
 * fitted image would show them a claim they cannot check.
 *
 * Geometry: defect circles are in the image's natural pixel space. The content
 * layer is laid out at the container's width, so natural coordinates map through
 * a fit factor, then through the pan/zoom transform. Circles scale with the
 * image (they mark an area); pin badges counter-scale so they stay legible.
 */
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
  data() {
    return {
      zoom: 1,
      tx: 0,
      ty: 0,
      fit: 1, // displayed px per natural px at zoom 1
      dragging: false,
      moved: false,
      origin: null,
      observer: null,
    }
  },
  computed: {
    pins() {
      return [...this.defects]
        .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
        .map((defect) => ({
          defect,
          cx: defect.circle.cx,
          cy: defect.circle.cy,
          r: defect.circle.radius,
          ring: RING_COLORS[defect.severity] || 'stroke-neutral-400',
          badge: PIN_COLORS[defect.severity] || 'bg-neutral-400',
          closed: CLOSED_STATES.includes(defect.status),
        }))
    },
    transform() {
      return `translate(${this.tx}px, ${this.ty}px) scale(${this.zoom})`
    },
    zoomLabel() {
      return `${Math.round(this.zoom * 100)}%`
    },
    canReset() {
      return this.zoom !== 1 || this.tx !== 0 || this.ty !== 0
    },
  },
  watch: {
    selectedId(id) {
      const pin = this.pins.find((p) => p.defect.id === id)
      // Only follow the selection when already magnified; yanking the viewport
      // around at fit-to-screen would be disorienting rather than helpful.
      if (pin && this.zoom > 1.2) this.centerOn(pin)
    },
    src() {
      this.reset()
    },
  },
  mounted() {
    this.measure()
    this.observer = new ResizeObserver(this.measure)
    this.observer.observe(this.$refs.viewport)
  },
  beforeUnmount() {
    this.observer?.disconnect()
  },
  methods: {
    measure() {
      const viewport = this.$refs.viewport
      if (viewport && this.width) this.fit = viewport.clientWidth / this.width
    },

    clamp(value) {
      return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value))
    },

    /** Zoom about a point in viewport coordinates, keeping it visually fixed. */
    zoomAt(nextZoom, px, py) {
      const zoom = this.clamp(nextZoom)
      const ratio = zoom / this.zoom
      this.tx = px - (px - this.tx) * ratio
      this.ty = py - (py - this.ty) * ratio
      this.zoom = zoom
      if (zoom === 1) this.reset()
      else this.constrain()
    },

    onWheel(event) {
      event.preventDefault()
      const box = this.$refs.viewport.getBoundingClientRect()
      const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2
      this.zoomAt(this.zoom * factor, event.clientX - box.left, event.clientY - box.top)
    },

    zoomBy(factor) {
      const box = this.$refs.viewport.getBoundingClientRect()
      this.zoomAt(this.zoom * factor, box.width / 2, box.height / 2)
    },

    reset() {
      this.zoom = 1
      this.tx = 0
      this.ty = 0
    },

    /** Keep the image overlapping the viewport so it can't be dragged off-screen. */
    constrain() {
      const viewport = this.$refs.viewport
      if (!viewport) return
      const w = viewport.clientWidth
      const h = this.height * this.fit
      const scaledW = w * this.zoom
      const scaledH = h * this.zoom

      this.tx = Math.min(0, Math.max(w - scaledW, this.tx))
      this.ty = Math.min(0, Math.max(Math.min(0, h - scaledH), this.ty))
    },

    /** Bring a defect to the centre of the viewport, magnifying if needed. */
    centerOn(pin, minZoom = 2.5) {
      const viewport = this.$refs.viewport
      if (!viewport) return
      this.zoom = this.clamp(Math.max(this.zoom, minZoom))
      this.tx = viewport.clientWidth / 2 - pin.cx * this.fit * this.zoom
      this.ty = viewport.clientHeight / 2 - pin.cy * this.fit * this.zoom
      this.constrain()
    },

    inspect(pin) {
      this.$emit('select', pin.defect)
      this.centerOn(pin)
    },

    onPointerDown(event) {
      if (this.zoom === 1) return
      this.dragging = true
      this.moved = false
      this.origin = { x: event.clientX - this.tx, y: event.clientY - this.ty }
      event.currentTarget.setPointerCapture?.(event.pointerId)
    },

    onPointerMove(event) {
      if (!this.dragging) return
      this.moved = true
      this.tx = event.clientX - this.origin.x
      this.ty = event.clientY - this.origin.y
      this.constrain()
    },

    onPointerUp() {
      this.dragging = false
    },

    onDoubleClick(event) {
      const box = this.$refs.viewport.getBoundingClientRect()
      const px = event.clientX - box.left
      const py = event.clientY - box.top
      if (this.zoom > 1) this.reset()
      else this.zoomAt(3, px, py)
    },

    // Clicking a pin must not also register as the end of a pan.
    onPinClick(pin) {
      if (!this.moved) this.inspect(pin)
    },
  },
}
</script>

<template>
  <div class="relative">
    <div
      ref="viewport"
      class="relative overflow-hidden rounded-lg bg-neutral-900 select-none"
      :class="zoom > 1 ? (dragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-zoom-in'"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="onPointerUp"
      @dblclick="onDoubleClick"
    >
      <div class="origin-top-left" :style="{ transform, transition: dragging ? 'none' : 'transform 140ms ease-out' }">
        <img :src="src" alt="Asset under review" class="block w-full" draggable="false" />

        <!-- Annotations live in the image's own coordinate space. -->
        <svg
          class="pointer-events-none absolute inset-0 size-full"
          :viewBox="`0 0 ${width} ${height}`"
          preserveAspectRatio="none"
        >
          <circle
            v-for="pin in pins"
            :key="pin.defect.id"
            :cx="pin.cx"
            :cy="pin.cy"
            :r="pin.r"
            fill="none"
            :class="pin.ring"
            :stroke-width="(selectedId === pin.defect.id ? 5 : 3) / zoom"
            :opacity="pin.closed ? 0.35 : 1"
          />
        </svg>

        <!-- Badges counter-scale so they stay readable at any magnification. -->
        <button
          v-for="pin in pins"
          :key="`badge-${pin.defect.id}`"
          type="button"
          class="absolute flex size-7 items-center justify-center rounded-full text-xs font-bold text-black ring-2 transition"
          :class="[
            pin.badge,
            selectedId === pin.defect.id ? 'ring-white' : 'ring-black/60',
            pin.closed ? 'opacity-40' : '',
          ]"
          :style="{
            left: `${((pin.cx - pin.r * 0.7071) / width) * 100}%`,
            top: `${((pin.cy - pin.r * 0.7071) / height) * 100}%`,
            transform: `translate(-50%, -50%) scale(${1 / zoom})`,
          }"
          :aria-label="`Pin ${pin.defect.pin}: ${pin.defect.comment}`"
          @click.stop="onPinClick(pin)"
        >
          {{ pin.defect.pin }}
        </button>
      </div>

      <!-- Controls -->
      <div class="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg border border-neutral-700 bg-neutral-900/90 p-1 backdrop-blur">
        <button
          type="button"
          class="rounded px-2 py-1 text-sm hover:bg-neutral-800"
          aria-label="Zoom out"
          @click="zoomBy(1 / 1.4)"
        >
          −
        </button>
        <span class="min-w-12 text-center font-mono text-xs text-neutral-400">{{ zoomLabel }}</span>
        <button
          type="button"
          class="rounded px-2 py-1 text-sm hover:bg-neutral-800"
          aria-label="Zoom in"
          @click="zoomBy(1.4)"
        >
          +
        </button>
        <button
          v-if="canReset"
          type="button"
          class="rounded px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
          @click="reset"
        >
          Fit
        </button>
      </div>

      <p
        v-if="zoom === 1"
        class="pointer-events-none absolute bottom-3 left-3 rounded bg-neutral-900/80 px-2 py-1 text-xs text-neutral-400 backdrop-blur"
      >
        Scroll or double-click to zoom · click a pin to inspect it
      </p>
    </div>
  </div>
</template>
