<script>
import { severityRank } from '@/domain/defects'

const SEVERITY_HEX = { blocker: '#E24B4A', warning: '#EF9F27', nitpick: '#378ADD' }
const CLOSED_STATES = ['verified_resolved', 'dismissed', 'override_approved']
const MIN_ZOOM = 1
const MAX_ZOOM = 8
//: Freehand paths keep at most this many points; further moves thin themselves out.
const MAX_PATH_POINTS = 400

/**
 * The review canvas: zoom, pan, and frame.io-style drawing.
 *
 * Everything on the image lives in its natural pixel space — the agent's defect
 * circles, human thread shapes, and the shape currently being drawn — and one
 * transform maps it all to the screen. Screen -> natural is the inverse of that
 * transform, so a drawing made at 300% zoom lands exactly where the cursor was.
 */
export default {
  name: 'ReviewCanvas',
  props: {
    src: { type: String, required: true },
    width: { type: Number, required: true },
    height: { type: Number, required: true },
    defects: { type: Array, default: () => [] },
    threads: { type: Array, default: () => [] }, // [{ thread, comments }]
    pendingShapes: { type: Array, default: () => [] },
    tool: { type: String, default: 'select' },
    color: { type: String, default: '#E24B4A' },
    selectedId: { type: String, default: '' },
  },
  emits: ['select', 'shape'],
  data() {
    return {
      zoom: 1,
      tx: 0,
      ty: 0,
      fit: 1,
      dragging: false,
      moved: false,
      origin: null,
      draft: null, // shape-in-progress, natural coords
      observer: null,
    }
  },
  computed: {
    pins() {
      return [...this.defects]
        .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
        .map((defect) => ({
          id: defect.id,
          kind: 'defect',
          pin: defect.pin,
          cx: defect.circle.cx,
          cy: defect.circle.cy,
          r: defect.circle.radius,
          color: SEVERITY_HEX[defect.severity] || '#888',
          closed: CLOSED_STATES.includes(defect.status),
          payload: defect,
        }))
    },
    threadPins() {
      return this.threads.map(({ thread }) => {
        const box = this.bboxOf(thread.shapes)
        return {
          id: thread.id,
          kind: 'thread',
          pin: thread.pin,
          x: box.left,
          y: box.top,
          cx: (box.left + box.right) / 2,
          cy: (box.top + box.bottom) / 2,
          shapes: thread.shapes,
          color: thread.shapes[0]?.color || '#378ADD',
          closed: thread.resolved,
          payload: thread,
        }
      })
    },
    transform() {
      return `translate(${this.tx}px, ${this.ty}px) scale(${this.zoom})`
    },
    zoomLabel() {
      return `${Math.round(this.zoom * 100)}%`
    },
    drawing() {
      return this.tool !== 'select'
    },
    cursor() {
      if (this.drawing) return 'cursor-crosshair'
      if (this.zoom > 1) return this.dragging ? 'cursor-grabbing' : 'cursor-grab'
      return 'cursor-zoom-in'
    },
    strokeWidth() {
      // Keep strokes visually constant across zoom, in natural units.
      return Math.max(2, (this.width / 300) * 1.2) / this.zoom
    },
  },
  watch: {
    src() {
      this.resetView()
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

    bboxOf(shapes) {
      let left = Infinity
      let top = Infinity
      let right = -Infinity
      let bottom = -Infinity
      for (const shape of shapes) {
        const points = shape.points
        if (shape.kind === 'circle') {
          left = Math.min(left, points[0] - points[2])
          top = Math.min(top, points[1] - points[2])
          right = Math.max(right, points[0] + points[2])
          bottom = Math.max(bottom, points[1] + points[2])
        } else if (shape.kind === 'rect') {
          left = Math.min(left, points[0])
          top = Math.min(top, points[1])
          right = Math.max(right, points[0] + points[2])
          bottom = Math.max(bottom, points[1] + points[3])
        } else {
          for (let i = 0; i < points.length; i += 2) {
            left = Math.min(left, points[i])
            top = Math.min(top, points[i + 1])
            right = Math.max(right, points[i])
            bottom = Math.max(bottom, points[i + 1])
          }
        }
      }
      return { left, top, right, bottom }
    },

    toNatural(event) {
      const box = this.$refs.viewport.getBoundingClientRect()
      const x = (event.clientX - box.left - this.tx) / (this.fit * this.zoom)
      const y = (event.clientY - box.top - this.ty) / (this.fit * this.zoom)
      return {
        x: Math.max(0, Math.min(this.width, x)),
        y: Math.max(0, Math.min(this.height, y)),
      }
    },

    // --- zoom and pan ---

    clampZoom(value) {
      return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value))
    },

    zoomAt(next, px, py) {
      const zoom = this.clampZoom(next)
      const ratio = zoom / this.zoom
      this.tx = px - (px - this.tx) * ratio
      this.ty = py - (py - this.ty) * ratio
      this.zoom = zoom
      if (zoom === 1) this.resetView()
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

    resetView() {
      this.zoom = 1
      this.tx = 0
      this.ty = 0
    },

    constrain() {
      const viewport = this.$refs.viewport
      if (!viewport) return
      const w = viewport.clientWidth
      const h = this.height * this.fit
      this.tx = Math.min(0, Math.max(w - w * this.zoom, this.tx))
      this.ty = Math.min(0, Math.max(Math.min(0, h - h * this.zoom), this.ty))
    },

    centerOn(point, minZoom = 2.5) {
      const viewport = this.$refs.viewport
      if (!viewport) return
      this.zoom = this.clampZoom(Math.max(this.zoom, minZoom))
      this.tx = viewport.clientWidth / 2 - point.cx * this.fit * this.zoom
      this.ty = viewport.clientHeight / 2 - point.cy * this.fit * this.zoom
      this.constrain()
    },

    // --- pointer flow: draw when a tool is armed, otherwise pan ---

    onPointerDown(event) {
      if (this.drawing) {
        const point = this.toNatural(event)
        this.draft =
          this.tool === 'path'
            ? { kind: 'path', points: [point.x, point.y], color: this.color }
            : { kind: this.tool, start: point, end: point, color: this.color }
        event.currentTarget.setPointerCapture?.(event.pointerId)
        return
      }
      if (this.zoom === 1) return
      this.dragging = true
      this.moved = false
      this.origin = { x: event.clientX - this.tx, y: event.clientY - this.ty }
      event.currentTarget.setPointerCapture?.(event.pointerId)
    },

    onPointerMove(event) {
      if (this.draft) {
        const point = this.toNatural(event)
        if (this.draft.kind === 'path') {
          const pts = this.draft.points
          if (pts.length >= MAX_PATH_POINTS * 2) {
            this.draft.points = pts.filter((_, i) => i < 2 || i % 4 < 2)
          }
          this.draft.points.push(point.x, point.y)
        } else {
          this.draft.end = point
        }
        return
      }
      if (!this.dragging) return
      this.moved = true
      this.tx = event.clientX - this.origin.x
      this.ty = event.clientY - this.origin.y
      this.constrain()
    },

    onPointerUp() {
      if (this.draft) {
        const shape = this.finishDraft(this.draft)
        this.draft = null
        if (shape) this.$emit('shape', shape)
        return
      }
      this.dragging = false
    },

    /** Convert a draft into the wire Shape format; drop accidental dots. */
    finishDraft(draft) {
      const round = (value) => Math.round(value * 10) / 10
      if (draft.kind === 'path') {
        if (draft.points.length < 4) return null
        return { kind: 'path', points: draft.points.map(round), color: draft.color }
      }
      const { start, end } = draft
      if (draft.kind === 'circle') {
        const r = Math.hypot(end.x - start.x, end.y - start.y)
        if (r < 4) return null
        return { kind: 'circle', points: [round(start.x), round(start.y), round(r)], color: draft.color }
      }
      if (draft.kind === 'rect') {
        const x = Math.min(start.x, end.x)
        const y = Math.min(start.y, end.y)
        const w = Math.abs(end.x - start.x)
        const h = Math.abs(end.y - start.y)
        if (w < 4 || h < 4) return null
        return { kind: 'rect', points: [round(x), round(y), round(w), round(h)], color: draft.color }
      }
      if (Math.hypot(end.x - start.x, end.y - start.y) < 4) return null
      return {
        kind: 'arrow',
        points: [round(start.x), round(start.y), round(end.x), round(end.y)],
        color: draft.color,
      }
    },

    draftAsShape() {
      if (!this.draft) return null
      if (this.draft.kind === 'path') return this.draft
      const { start, end, kind, color } = this.draft
      if (kind === 'circle') {
        return { kind, points: [start.x, start.y, Math.hypot(end.x - start.x, end.y - start.y)], color }
      }
      if (kind === 'rect') {
        return {
          kind,
          points: [
            Math.min(start.x, end.x),
            Math.min(start.y, end.y),
            Math.abs(end.x - start.x),
            Math.abs(end.y - start.y),
          ],
          color,
        }
      }
      return { kind, points: [start.x, start.y, end.x, end.y], color }
    },

    arrowHead(points) {
      const [x1, y1, x2, y2] = points
      const angle = Math.atan2(y2 - y1, x2 - x1)
      const size = this.strokeWidth * 4
      const left = angle + Math.PI * 0.85
      const right = angle - Math.PI * 0.85
      return `${x2},${y2} ${x2 + size * Math.cos(left)},${y2 + size * Math.sin(left)} ${
        x2 + size * Math.cos(right)
      },${y2 + size * Math.sin(right)}`
    },

    pathData(points) {
      let d = `M ${points[0]} ${points[1]}`
      for (let i = 2; i < points.length; i += 2) d += ` L ${points[i]} ${points[i + 1]}`
      return d
    },

    onDoubleClick(event) {
      if (this.drawing) return
      const box = this.$refs.viewport.getBoundingClientRect()
      if (this.zoom > 1) this.resetView()
      else this.zoomAt(3, event.clientX - box.left, event.clientY - box.top)
    },

    onBadgeClick(item) {
      if (this.moved || this.drawing) return
      this.$emit('select', item)
      this.centerOn(item)
    },
  },
}
</script>

<template>
  <div
    ref="viewport"
    class="relative overflow-hidden rounded-lg bg-[#131416] select-none touch-none"
    :class="cursor"
    @wheel="onWheel"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @dblclick="onDoubleClick"
  >
    <div
      class="origin-top-left"
      :style="{ transform, transition: dragging || draft ? 'none' : 'transform 140ms ease-out' }"
    >
      <img :src="src" alt="Asset under review" class="block w-full" draggable="false" />

      <svg
        class="pointer-events-none absolute inset-0 size-full"
        :viewBox="`0 0 ${width} ${height}`"
        preserveAspectRatio="none"
      >
        <!-- Agent defects: circles -->
        <circle
          v-for="pin in pins"
          :key="pin.id"
          :cx="pin.cx"
          :cy="pin.cy"
          :r="pin.r"
          fill="none"
          :stroke="pin.color"
          :stroke-width="selectedId === pin.id ? strokeWidth * 1.8 : strokeWidth"
          :opacity="pin.closed ? 0.35 : 1"
        />

        <!-- Human threads: drawn shapes -->
        <g
          v-for="item in threadPins"
          :key="item.id"
          :opacity="item.closed ? 0.35 : 1"
        >
          <template v-for="(shape, index) in item.shapes" :key="index">
            <circle
              v-if="shape.kind === 'circle'"
              :cx="shape.points[0]"
              :cy="shape.points[1]"
              :r="shape.points[2]"
              fill="none"
              :stroke="shape.color"
              :stroke-width="selectedId === item.id ? strokeWidth * 1.8 : strokeWidth"
            />
            <rect
              v-else-if="shape.kind === 'rect'"
              :x="shape.points[0]"
              :y="shape.points[1]"
              :width="shape.points[2]"
              :height="shape.points[3]"
              fill="none"
              :stroke="shape.color"
              :stroke-width="selectedId === item.id ? strokeWidth * 1.8 : strokeWidth"
            />
            <g v-else-if="shape.kind === 'arrow'">
              <line
                :x1="shape.points[0]"
                :y1="shape.points[1]"
                :x2="shape.points[2]"
                :y2="shape.points[3]"
                :stroke="shape.color"
                :stroke-width="strokeWidth"
              />
              <polygon :points="arrowHead(shape.points)" :fill="shape.color" />
            </g>
            <path
              v-else
              :d="pathData(shape.points)"
              fill="none"
              :stroke="shape.color"
              :stroke-width="strokeWidth"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </template>
        </g>

        <!-- Pending shapes for the comment being composed -->
        <g v-for="(shape, index) in pendingShapes" :key="`pending-${index}`">
          <circle
            v-if="shape.kind === 'circle'"
            :cx="shape.points[0]" :cy="shape.points[1]" :r="shape.points[2]"
            fill="none" :stroke="shape.color" :stroke-width="strokeWidth" stroke-dasharray="6 4"
          />
          <rect
            v-else-if="shape.kind === 'rect'"
            :x="shape.points[0]" :y="shape.points[1]"
            :width="shape.points[2]" :height="shape.points[3]"
            fill="none" :stroke="shape.color" :stroke-width="strokeWidth" stroke-dasharray="6 4"
          />
          <g v-else-if="shape.kind === 'arrow'">
            <line
              :x1="shape.points[0]" :y1="shape.points[1]"
              :x2="shape.points[2]" :y2="shape.points[3]"
              :stroke="shape.color" :stroke-width="strokeWidth" stroke-dasharray="6 4"
            />
            <polygon :points="arrowHead(shape.points)" :fill="shape.color" />
          </g>
          <path
            v-else
            :d="pathData(shape.points)"
            fill="none" :stroke="shape.color" :stroke-width="strokeWidth"
            stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="6 4"
          />
        </g>

        <!-- Live draft while the pointer is down -->
        <template v-if="draftAsShape()">
          <circle
            v-if="draftAsShape().kind === 'circle'"
            :cx="draftAsShape().points[0]" :cy="draftAsShape().points[1]" :r="draftAsShape().points[2]"
            fill="none" :stroke="color" :stroke-width="strokeWidth"
          />
          <rect
            v-else-if="draftAsShape().kind === 'rect'"
            :x="draftAsShape().points[0]" :y="draftAsShape().points[1]"
            :width="draftAsShape().points[2]" :height="draftAsShape().points[3]"
            fill="none" :stroke="color" :stroke-width="strokeWidth"
          />
          <line
            v-else-if="draftAsShape().kind === 'arrow'"
            :x1="draftAsShape().points[0]" :y1="draftAsShape().points[1]"
            :x2="draftAsShape().points[2]" :y2="draftAsShape().points[3]"
            :stroke="color" :stroke-width="strokeWidth"
          />
          <path
            v-else
            :d="pathData(draftAsShape().points)"
            fill="none" :stroke="color" :stroke-width="strokeWidth"
            stroke-linecap="round" stroke-linejoin="round"
          />
        </template>
      </svg>

      <!-- Numbered badges, counter-scaled to stay legible -->
      <button
        v-for="item in [...pins, ...threadPins]"
        :key="`badge-${item.id}`"
        type="button"
        class="absolute flex size-7 items-center justify-center rounded-full text-xs font-bold text-black ring-2 transition"
        :class="selectedId === item.id ? 'ring-white' : 'ring-black/60'"
        :style="{
          left: `${((item.kind === 'defect' ? item.cx - item.r * 0.7071 : item.x) / width) * 100}%`,
          top: `${((item.kind === 'defect' ? item.cy - item.r * 0.7071 : item.y) / height) * 100}%`,
          transform: `translate(-50%, -50%) scale(${1 / zoom})`,
          background: item.color,
          opacity: item.closed ? 0.4 : 1,
        }"
        :aria-label="`Pin ${item.pin}`"
        @click.stop="onBadgeClick(item)"
      >
        {{ item.pin }}
      </button>
    </div>

    <!-- Zoom controls -->
    <div
      class="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg border border-neutral-700 bg-neutral-900/90 p-1 backdrop-blur"
    >
      <button type="button" class="rounded px-2 py-1 text-sm hover:bg-neutral-800" aria-label="Zoom out" @click="zoomBy(1 / 1.4)">−</button>
      <span class="min-w-12 text-center font-mono text-xs text-neutral-400">{{ zoomLabel }}</span>
      <button type="button" class="rounded px-2 py-1 text-sm hover:bg-neutral-800" aria-label="Zoom in" @click="zoomBy(1.4)">+</button>
      <button
        v-if="zoom !== 1 || tx !== 0 || ty !== 0"
        type="button"
        class="rounded px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
        @click="resetView"
      >
        Fit
      </button>
    </div>
  </div>
</template>
