<script>
import { mapState } from 'pinia'

import CompareView from '@/components/CompareView.vue'
import { comparePair, flowNodes, isAgentVersion, slotPill, stanceFor, TONE_HEX, versionTone } from '@/domain/slots'
import { shortDate } from '@/domain/time'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'
import { useSlotsStore } from '@/stores/slots'

const NODE_W = 168
const COL_W = 196
const ROW_H = 148

export default {
  name: 'SlotFlowPage',
  components: { CompareView },
  props: {
    projectId: { type: String, required: true },
    slotId: { type: String, required: true },
  },
  data() {
    return {
      NODE_W,
      COL_W,
      ROW_H,
      selected: null,
      hovered: null,
      hoverBox: null,
      zoom: 1,
      pan: { x: 0, y: 0 },
      panning: false,
      panFrom: { x: 0, y: 0 },
      collapsed: {},
      busy: false,
      actionError: '',
    }
  },
  computed: {
    ...mapState(useSlotsStore, ['slots', 'loading', 'error']),
    slot() {
      return useSlotsStore().slotById(this.slotId)
    },
    canApprove() {
      return useProjectsStore().can('approve_image')
    },
    canFix() {
      return useProjectsStore().can('submit_fix')
    },
    canUpload() {
      return useProjectsStore().can('upload_images')
    },
    nodes() {
      return this.slot ? flowNodes(this.slot) : []
    },
    byId() {
      return Object.fromEntries(this.nodes.map((n) => [n.id, n]))
    },
    /** Real parentage, ignoring what is folded away. */
    allChildrenOf() {
      const map = {}
      for (const n of this.nodes) (map[n.parent] ??= []).push(n)
      return map
    },
    /** What the canvas draws: a collapsed node keeps its children out of layout. */
    childrenOf() {
      const map = {}
      for (const n of this.nodes) {
        if (n.parent && this.collapsed[n.parent]) continue
        if (n.parent && this.hiddenUnderCollapse.has(n.parent)) continue
        ;(map[n.parent] ??= []).push(n)
      }
      return map
    },
    /** Every descendant of a collapsed node, so nothing orphaned gets drawn. */
    hiddenUnderCollapse() {
      const hidden = new Set()
      const walk = (id) => {
        for (const child of this.allChildrenOf[id] || []) {
          hidden.add(child.id)
          walk(child.id)
        }
      }
      for (const id of Object.keys(this.collapsed)) if (this.collapsed[id]) walk(id)
      return hidden
    },
    roots() {
      return this.childrenOf[null] || []
    },
    rows() {
      return this.outline()
    },
    /**
     * Classic tree layout: leaves take the next free column, every parent centres
     * over its children. The slot sits at the top; everything hangs beneath it.
     */
    layout() {
      const column = {}
      let cursor = 0
      const place = (id) => {
        const kids = this.childrenOf[id] || []
        if (!kids.length) {
          column[id] = cursor
          cursor += 1
          return
        }
        kids.forEach((kid) => place(kid.id))
        column[id] = (column[kids[0].id] + column[kids[kids.length - 1].id]) / 2
      }
      this.roots.forEach((root) => place(root.id))

      const depth = Object.fromEntries(this.rows.map((r) => [r.node.id, r.depth + 1]))
      const deepest = Math.max(0, ...this.rows.map((r) => r.depth)) + 1
      const rootColumn = this.roots.length
        ? (column[this.roots[0].id] + column[this.roots[this.roots.length - 1].id]) / 2
        : 0

      return {
        column,
        depth,
        rootColumn,
        width: Math.max(1, cursor) * COL_W,
        height: (deepest + 1) * ROW_H + 30,
      }
    },
    approvedIds() {
      return this.nodes
        .filter((n) => n.variant.approved && n.version.image.approved_by)
        .map((n) => n.id)
    },
    /** Every ancestor of an approved version — the lineage that shipped. */
    onWinningPath() {
      const path = new Set()
      for (const id of this.approvedIds) {
        let cur = this.byId[id]
        while (cur) {
          path.add(cur.id)
          cur = cur.parent ? this.byId[cur.parent] : null
        }
      }
      return path
    },
    pill() {
      return this.slot ? slotPill(this.slot) : null
    },
    summary() {
      if (!this.slot) return ''
      const versions = this.nodes.length
      const branches = this.slot.variants.length
      return `${branches} variant${branches === 1 ? '' : 's'} · ${versions} version${versions === 1 ? '' : 's'} · ${this.pill.label}`
    },
    selectedNode() {
      return (this.selected && this.byId[this.selected]) || null
    },
    /** Compare needs a pair (decision 25); a single-version slot has none. */
    comparable() {
      return comparePair(this.nodes) !== null
    },
    comparing() {
      return this.$route.query.compare === '1' && this.comparable
    },
    /** The agent's recommendation (decision 21): computed facts, never prose. */
    stance() {
      return this.slot ? stanceFor(this.slot) : null
    },
    previewStyle() {
      if (!this.hoverBox) return { display: 'none' }
      const node = this.byId[this.hovered]
      const width = 280
      const height = Math.round(width / this.ratioOf(node)) + 70
      const left =
        this.hoverBox.left - width - 18 > 12
          ? this.hoverBox.left - width - 18
          : this.hoverBox.right + 18
      const top = Math.min(
        Math.max(12, this.hoverBox.top + this.hoverBox.height / 2 - height / 2),
        window.innerHeight - height - 24,
      )
      return { left: `${left}px`, top: `${top}px`, width: `${width}px` }
    },
  },
  watch: {
    /** A refetched slot list replaces the objects; keep the selection meaningful. */
    slot(current) {
      if (current && this.selected && !this.nodes.some((n) => n.id === this.selected)) {
        this.selected = null
      }
    },
  },
  async created() {
    await useProjectsStore().fetchOne(this.projectId)
    if (!this.slot) await useSlotsStore().fetchSlots(this.projectId)
    // Land oriented: the approved version if there is one, else the newest node.
    this.selected =
      this.approvedIds[0] || this.nodes[this.nodes.length - 1]?.id || null
    this.$nextTick(this.fit)
  },
  methods: {
    shortDate,
    statusOf(node) {
      if (this.isApproved(node)) return { label: 'Approved', dot: TONE_HEX.green }
      const tone = versionTone(node.version)
      const labels = {
        red: 'Failed',
        busy: 'Reviewing…',
        amber: `${node.version.open_defects} open`,
        green: 'Clean',
      }
      return { label: labels[tone], dot: TONE_HEX[tone] }
    },
    isApproved(node) {
      return node.variant.approved && node.version.image.approved_by !== null
    },
    isDraft(node) {
      return isAgentVersion(node.version)
    },
    async discardSelected() {
      if (!this.selectedNode) return
      this.busy = true
      this.actionError = ''
      try {
        await useSlotsStore().discardDraft(this.projectId, this.selectedNode.id)
        this.selected = null
      } catch (error) {
        this.actionError = error.message
      } finally {
        this.busy = false
      }
    },
    /** Once anything is approved, everything off the shipped lineage dims. */
    isArchived(node) {
      return this.approvedIds.length > 0 && !this.onWinningPath.has(node.id)
    },
    ratioOf(node) {
      const { width, height } = node.version.image
      return width && height ? width / height : 1
    },
    hiddenCount(node) {
      let total = 0
      const walk = (id) => {
        for (const child of this.allChildrenOf[id] || []) {
          total += 1
          walk(child.id)
        }
      }
      walk(node.id)
      return total
    },
    toggleCollapse(node) {
      this.collapsed = { ...this.collapsed, [node.id]: !this.collapsed[node.id] }
    },
    /** Elbow, not curve: parent drops to a shared bus, then into each child. */
    edge(node) {
      const l = this.layout
      const parentCol = node.parent === null ? l.rootColumn : l.column[node.parent]
      const parentDepth = node.parent === null ? 0 : l.depth[node.parent]
      const x1 = parentCol * COL_W + NODE_W / 2
      const y1 = parentDepth * ROW_H + (node.parent === null ? 74 : 112)
      const x2 = l.column[node.id] * COL_W + NODE_W / 2
      const y2 = l.depth[node.id] * ROW_H + 4
      if (Math.abs(x1 - x2) < 1) return `M ${x1} ${y1} L ${x2} ${y2}`
      const bus = y2 - 22
      return `M ${x1} ${y1} L ${x1} ${bus} L ${x2} ${bus} L ${x2} ${y2}`
    },
    /** Scale and centre the whole tree in the viewport. */
    fit() {
      const port = this.$refs.viewport
      if (!port) return
      const scale = Math.min(
        (port.clientWidth - 96) / this.layout.width,
        (port.clientHeight - 96) / this.layout.height,
        1,
      )
      this.zoom = Math.max(0.15, Math.min(1, scale))
      this.pan = {
        x: (port.clientWidth - this.layout.width * this.zoom) / 2,
        y: 32,
      }
    },
    /** Zoom about the pointer, so whatever is under the cursor stays under it. */
    onWheel(event) {
      const port = this.$refs.viewport
      if (!port) return
      const rect = port.getBoundingClientRect()
      const px = event.clientX - rect.left
      const py = event.clientY - rect.top
      const next = Math.max(0.15, Math.min(2, this.zoom * Math.exp(-event.deltaY * 0.0015)))
      const k = next / this.zoom
      this.pan = { x: px - (px - this.pan.x) * k, y: py - (py - this.pan.y) * k }
      this.zoom = next
    },
    onPanStart(event) {
      // A press on a control is that control's, not a drag of the canvas beneath
      // it. `label` matters as much as `button`: capturing the pointer retargets
      // the click, so a label wrapping a file input would silently never open it.
      if (event.target.closest('button, a, input, label')) return
      this.panning = true
      this.hovered = null
      this.panFrom = { x: event.clientX - this.pan.x, y: event.clientY - this.pan.y }
      event.currentTarget.setPointerCapture?.(event.pointerId)
    },
    onPanMove(event) {
      if (!this.panning) return
      this.pan = { x: event.clientX - this.panFrom.x, y: event.clientY - this.panFrom.y }
    },
    onPanEnd(event) {
      this.panning = false
      event.currentTarget.releasePointerCapture?.(event.pointerId)
    },
    nudgeZoom(direction) {
      const port = this.$refs.viewport
      if (!port) return
      const rect = port.getBoundingClientRect()
      this.onWheel({
        clientX: rect.left + port.clientWidth / 2,
        clientY: rect.top + port.clientHeight / 2,
        deltaY: direction * -120,
      })
    },
    onEnter(node, event) {
      this.hovered = node.id
      this.hoverBox = event.currentTarget.getBoundingClientRect()
    },
    onLeave() {
      this.hovered = null
      this.hoverBox = null
    },
    openReview(node) {
      this.$router.push({
        name: 'review',
        params: { projectId: this.projectId, imageId: node.id },
      })
    },
    /**
     * A new competing candidate for the slot: a fresh trunk beside the others,
     * not a fix of anything. It hangs off the slot node because that is where
     * variants branch from, so the affordance sits where the split happens.
     */
    async onVariantFile(fileList) {
      const file = Array.from(fileList).find((entry) => entry.type.startsWith('image/'))
      if (!file) return
      this.busy = true
      this.actionError = ''
      try {
        const created = await useSlotsStore().addVariant(this.projectId, this.slotId, file)
        if (created?.id) this.selected = created.id
        this.$nextTick(this.fit)
      } catch (error) {
        this.actionError = error.message
      } finally {
        this.busy = false
      }
    },

    /** A new fix under the selected version — a branch if one already exists. */
    async onBranchFile(fileList) {
      const file = Array.from(fileList).find((entry) => entry.type.startsWith('image/'))
      if (!file || !this.selectedNode) return
      this.busy = true
      this.actionError = ''
      try {
        await useReviewStore().submitFix(this.projectId, this.selectedNode.id, file)
        await useSlotsStore().fetchSlots(this.projectId)
      } catch (error) {
        this.actionError = error.message
      } finally {
        this.busy = false
      }
    },
    async approveSelected() {
      if (!this.selectedNode) return
      this.busy = true
      this.actionError = ''
      try {
        await useReviewStore().approveImage(this.projectId, this.selectedNode.id)
        await useSlotsStore().fetchSlots(this.projectId)
      } catch (error) {
        this.actionError = error.message
      } finally {
        this.busy = false
      }
    },
    outline(parent = null, depth = 0, acc = []) {
      for (const child of this.childrenOf[parent] || []) {
        acc.push({ node: child, depth })
        this.outline(child.id, depth + 1, acc)
      }
      return acc
    },
  },
}
</script>

<template>
  <!-- 49px is the app header above this page; the canvas owns everything below it. -->
  <div class="relative h-[calc(100vh-49px)] overflow-hidden">
    <!-- depth of field: grid + vignette so the cards read as floating -->
    <div
      class="pointer-events-none fixed inset-0"
      style="
        background-image:
          linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
        background-size: 40px 40px;
      "
    />
    <div
      class="pointer-events-none fixed inset-0"
      style="background: radial-gradient(ellipse at 50% 30%, transparent 18%, rgba(6, 6, 8, 0.85) 76%)"
    />

    <!-- header: where you are, and the canvas controls -->
    <header
      class="relative z-20 flex h-12 items-center gap-3 border-b border-edge-strong bg-ink/90 px-4 backdrop-blur xl:pr-[356px]"
    >
      <RouterLink
        :to="{ name: 'project', params: { projectId } }"
        class="text-xs text-neutral-500 hover:text-neutral-200"
      >
        ← Slots
      </RouterLink>
      <span class="truncate text-sm font-medium text-neutral-100">
        {{ slot?.name || 'Slot' }}
      </span>
      <span v-if="pill" class="flex items-center gap-1.5 text-[11px] text-neutral-400">
        <span
          class="size-1.5 rounded-full"
          :class="pill.tone === 'busy' ? 'animate-pulse' : ''"
          :style="{ background: pill.dot }"
        />
        {{ summary }}
      </span>

      <div class="ml-auto flex items-center gap-1">
        <button
          v-if="comparable"
          type="button"
          class="mr-1 rounded border border-neutral-600 px-2 py-0.5 text-xs text-neutral-200 hover:bg-edge"
          @click="$router.replace({ query: { ...$route.query, compare: '1' } })"
        >
          Compare
        </button>
        <button
          type="button"
          class="rounded border border-neutral-600 px-2 py-0.5 text-xs text-neutral-200 hover:bg-edge"
          aria-label="Zoom out"
          @click="nudgeZoom(-1)"
        >
          −
        </button>
        <span class="w-10 text-center font-mono text-[11px] text-neutral-300">
          {{ Math.round(zoom * 100) }}%
        </span>
        <button
          type="button"
          class="rounded border border-neutral-600 px-2 py-0.5 text-xs text-neutral-200 hover:bg-edge"
          aria-label="Zoom in"
          @click="nudgeZoom(1)"
        >
          +
        </button>
        <button
          type="button"
          class="ml-1 rounded border border-neutral-600 px-2 py-0.5 text-[11px] text-neutral-200 hover:bg-edge"
          @click="fit"
        >
          Fit
        </button>
      </div>
    </header>

    <div class="relative xl:pr-[340px]">
      <p v-if="loading && !slot" class="px-6 py-10 text-sm text-neutral-500">Loading slot…</p>
      <p v-else-if="error && !slot" class="px-6 py-10 text-sm text-blocker">{{ error }}</p>
      <p v-else-if="!slot" class="px-6 py-10 text-sm text-neutral-500">
        This slot no longer exists.
      </p>

      <!--
        A canvas, not a scroll area: drag to pan, wheel to zoom about the cursor,
        double-click to fit.
      -->
      <div
        v-else
        ref="viewport"
        class="relative h-[calc(100vh-97px)] touch-none select-none overflow-hidden"
        :class="panning ? 'cursor-grabbing' : 'cursor-grab'"
        @wheel.prevent="onWheel"
        @pointerdown="onPanStart"
        @pointermove="onPanMove"
        @pointerup="onPanEnd"
        @pointercancel="onPanEnd"
        @dblclick="fit"
      >
        <p class="pointer-events-none absolute bottom-3 left-4 z-10 text-[10px] text-neutral-500">
          drag to pan · scroll to zoom · double-click to fit
        </p>
        <div
          class="absolute left-0 top-0 origin-top-left"
          :style="{
            width: `${layout.width}px`,
            height: `${layout.height}px`,
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          }"
        >
          <div class="relative h-full w-full">
            <svg class="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
              <path
                v-for="row in rows"
                :key="`e-${row.node.id}`"
                :d="edge(row.node)"
                fill="none"
                stroke-linecap="round"
                :stroke="onWinningPath.has(row.node.id) ? '#5eead4' : '#8b8b96'"
                :stroke-width="onWinningPath.has(row.node.id) ? 2.5 : 2"
                :opacity="isArchived(row.node) ? 0.7 : 1"
              />
            </svg>

            <!-- the slot itself: the starting point, stated -->
            <div
              class="absolute rounded-2xl border border-neutral-500 bg-panel-2 px-4 py-3 text-center shadow-2xl shadow-black/60"
              :style="{
                width: `${NODE_W + 60}px`,
                left: `${layout.rootColumn * COL_W - 30}px`,
                top: '0px',
              }"
            >
              <div class="text-[10px] uppercase tracking-widest text-neutral-400">Slot</div>
              <div class="mt-0.5 truncate text-sm font-medium text-neutral-50">{{ slot.name }}</div>
              <div class="mt-1 text-[10px] leading-relaxed text-neutral-400">{{ summary }}</div>

              <!-- Variants branch from the slot, so the control to add one lives here. -->
              <label
                v-if="canUpload"
                class="absolute -bottom-3 left-1/2 -translate-x-1/2 cursor-pointer whitespace-nowrap rounded-full border border-neutral-500 bg-panel px-2 py-0.5 text-[10px] text-neutral-200 shadow-lg shadow-black/50 hover:border-neutral-300 hover:bg-edge"
                :class="busy ? 'pointer-events-none opacity-50' : ''"
              >
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  class="hidden"
                  @change="onVariantFile($event.target.files)"
                />
                {{ busy ? 'Uploading…' : '+ variant' }}
              </label>
            </div>

            <button
              v-for="row in rows"
              :key="row.node.id"
              type="button"
              class="absolute rounded-xl border p-2 text-left shadow-xl shadow-black/50 transition duration-150"
              :style="{
                width: `${NODE_W}px`,
                left: `${layout.column[row.node.id] * COL_W}px`,
                top: `${layout.depth[row.node.id] * ROW_H + 4}px`,
              }"
              :class="[
                isApproved(row.node)
                  ? 'border-teal-400/70 bg-teal-400/10 shadow-teal-500/10'
                  : isDraft(row.node)
                    ? 'border-dashed border-teal-400/60 bg-panel-2 hover:border-teal-300'
                    : 'border-edge-strong bg-panel-2 hover:border-neutral-500',
                isArchived(row.node) ? 'opacity-45 saturate-50' : '',
                selected === row.node.id ? 'ring-2 ring-neutral-300' : '',
                hovered === row.node.id ? 'z-10 -translate-y-0.5' : '',
              ]"
              @click="selected = row.node.id"
              @dblclick.stop="openReview(row.node)"
              @mouseenter="onEnter(row.node, $event)"
              @mouseleave="onLeave"
            >
              <div class="flex items-center gap-2.5">
                <img
                  :src="row.node.version.original_url"
                  :alt="row.node.label"
                  class="h-10 w-12 shrink-0 rounded object-cover ring-1 ring-inset ring-white/10"
                  draggable="false"
                />
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5">
                    <span class="font-mono text-xs text-neutral-100">{{ row.node.label }}</span>
                    <span
                      v-if="!row.node.parent"
                      class="rounded-full border border-neutral-600 px-1.5 text-[9px] text-neutral-300"
                    >var {{ row.node.variant.variant }}</span>
                    <span
                      v-if="isDraft(row.node) && !isApproved(row.node)"
                      class="rounded-full border border-dashed border-teal-400/60 px-1.5 text-[9px] text-teal-300"
                    >draft</span>
                  </div>
                  <div class="truncate text-[11px] text-neutral-400">
                    {{ row.node.version.uploader_name || 'unknown' }} ·
                    {{ shortDate(row.node.version.image.created_at) }}
                  </div>
                </div>
              </div>
              <div class="mt-1.5 flex items-center gap-1.5 text-[10px] text-neutral-300">
                <span
                  class="size-1.5 rounded-full"
                  :style="{ background: statusOf(row.node).dot }"
                />
                {{ statusOf(row.node).label }}
                <span
                  role="link"
                  class="ml-auto rounded px-1.5 py-0.5 text-[9px] text-neutral-400 hover:bg-edge hover:text-neutral-100"
                  @click.stop="openReview(row.node)"
                >Review ↗</span>
              </div>

              <!-- fold a subtree away; the count is what you are hiding -->
              <span
                v-if="(allChildrenOf[row.node.id] || []).length"
                class="absolute -bottom-2.5 left-1/2 -translate-x-1/2 rounded-full border border-neutral-500 bg-panel px-1.5 text-[9px] leading-4 text-neutral-300 hover:bg-edge"
                @click.stop="toggleCollapse(row.node)"
              >
                {{ collapsed[row.node.id] ? `+${hiddenCount(row.node)}` : '−' }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Upload failures must be visible from the canvas: the rail that used to
         carry them is hidden below xl, and "+ variant" needs no selection. -->
    <div
      v-if="actionError"
      class="fixed bottom-4 left-1/2 z-40 flex max-w-md -translate-x-1/2 items-center gap-3 rounded-lg border border-blocker/50 bg-panel-2 px-3 py-2 shadow-2xl shadow-black/70 xl:left-[calc(50%-170px)]"
    >
      <span class="text-xs text-blocker">{{ actionError }}</span>
      <button
        type="button"
        class="ml-auto text-xs text-neutral-500 hover:text-neutral-200"
        @click="actionError = ''"
      >
        Dismiss
      </button>
    </div>

    <!-- hover preview: the asset at its natural aspect, uncropped -->
    <div
      v-if="hovered && byId[hovered]"
      class="pointer-events-none fixed z-40 rounded-xl border border-neutral-600 bg-panel-2 p-2 shadow-2xl shadow-black/70"
      :style="previewStyle"
    >
      <img
        :src="byId[hovered].version.original_url"
        :alt="byId[hovered].label"
        class="w-full rounded-md ring-1 ring-inset ring-white/10"
        :style="{ aspectRatio: ratioOf(byId[hovered]) }"
      />
      <div class="mt-2 flex items-baseline gap-2 px-0.5">
        <span class="font-mono text-xs text-neutral-100">{{ byId[hovered].label }}</span>
        <span class="text-[11px] text-neutral-400">
          {{ byId[hovered].version.uploader_name || 'unknown' }}
        </span>
        <span class="ml-auto text-[11px] text-neutral-400">
          {{ shortDate(byId[hovered].version.image.created_at) }}
        </span>
      </div>
    </div>

    <!-- compare mode (decision 25): looking, not judging -->
    <CompareView
      v-if="comparing"
      :project-id="projectId"
      :nodes="nodes"
      @close="$router.replace({ query: { ...$route.query, compare: undefined, mode: undefined } })"
    />

    <!-- ═══ version rail: what is selected, and what you can do to it ═══ -->
    <aside
      class="fixed bottom-0 right-0 top-[49px] z-20 hidden w-[340px] flex-col border-l border-edge-strong bg-panel/95 backdrop-blur xl:flex"
    >
      <header class="border-b border-edge-strong px-4 py-3">
        <div class="text-[10px] uppercase tracking-widest text-neutral-400">Selected version</div>
        <div v-if="selectedNode" class="mt-0.5 flex items-center gap-2">
          <img
            :src="selectedNode.version.original_url"
            :alt="selectedNode.label"
            class="h-7 w-9 shrink-0 rounded object-cover ring-1 ring-inset ring-white/10"
          />
          <div class="min-w-0">
            <div class="font-mono text-xs text-neutral-50">
              {{ selectedNode.label }} · variant {{ selectedNode.variant.variant }}
            </div>
            <div class="truncate text-[11px] text-neutral-400">
              {{ selectedNode.version.uploader_name || 'unknown' }} ·
              {{ shortDate(selectedNode.version.image.created_at) }} ·
              {{ statusOf(selectedNode).label }}
            </div>
          </div>
        </div>
        <p v-else class="mt-1 text-[11px] text-neutral-500">Click a version in the tree.</p>
      </header>

      <div v-if="selectedNode" class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <img
          :src="selectedNode.version.original_url"
          :alt="selectedNode.label"
          class="w-full rounded-lg ring-1 ring-inset ring-white/10"
          :style="{ aspectRatio: ratioOf(selectedNode) }"
        />
        <dl class="mt-3 space-y-1.5 text-[11px]">
          <div class="flex justify-between">
            <dt class="text-neutral-500">Open defects</dt>
            <dd class="text-neutral-200">{{ selectedNode.version.open_defects }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-neutral-500">Status</dt>
            <dd class="text-neutral-200">{{ statusOf(selectedNode).label }}</dd>
          </div>
          <div v-if="isApproved(selectedNode)" class="flex justify-between">
            <dt class="text-neutral-500">Approved by</dt>
            <dd class="text-teal-200">
              {{ selectedNode.variant.approved_by_name || 'the owner' }}
            </dd>
          </div>
          <div v-if="isArchived(selectedNode)" class="flex justify-between">
            <dt class="text-neutral-500">Lineage</dt>
            <dd class="text-neutral-400">off the shipped path</dd>
          </div>
        </dl>

        <a
          v-if="isApproved(selectedNode)"
          :href="selectedNode.version.original_url"
          download
          class="mt-3 block rounded-md bg-teal-300 px-3 py-1.5 text-center text-xs font-medium text-neutral-900 hover:bg-teal-200"
        >
          Download approved asset
        </a>
      </div>
      <div v-else class="flex-1" />

      <!-- The stance (decision 21): the claim in facts, the proof one click away. -->
      <div v-if="stance" class="border-t border-edge-strong p-3">
        <div class="rounded-lg border border-teal-400/40 bg-teal-400/5 p-2.5">
          <p class="text-[10px] uppercase tracking-wide text-teal-300">My call</p>
          <p class="mt-1 text-xs text-neutral-200">
            I'd ship <span class="font-mono">v{{ stance.version.image.version }}</span>
            (variant {{ stance.variant }}){{ stance.draft ? ' — my draft' : '' }}
          </p>
          <ul class="mt-1 text-[10px] leading-relaxed text-neutral-400">
            <li v-for="fact in stance.facts" :key="fact">· {{ fact }}</li>
          </ul>
          <div class="mt-2 flex gap-1.5">
            <button
              type="button"
              class="flex-1 rounded-md bg-neutral-50 px-2 py-1 text-[11px] font-medium text-neutral-900"
              @click="selected = stance.imageId; openReview({ id: stance.imageId })"
            >
              Check it on review
            </button>
            <button
              v-if="stance.draft && canFix"
              type="button"
              :disabled="busy"
              class="rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-300 hover:bg-edge disabled:opacity-50"
              @click="selected = stance.imageId; discardSelected()"
            >
              Discard draft
            </button>
          </div>
          <p class="mt-1.5 text-center text-[9px] text-neutral-600">
            a recommendation, not a decision — approval stays yours
          </p>
        </div>
      </div>

      <div v-if="selectedNode" class="border-t border-edge-strong p-3">
        <button
          type="button"
          class="w-full rounded-md bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-white"
          @click="openReview(selectedNode)"
        >
          Open review
        </button>
        <div class="mt-1.5 flex gap-1.5">
          <label
            v-if="canFix"
            class="flex-1 cursor-pointer rounded-md border border-neutral-600 px-2 py-1 text-center text-[11px] text-neutral-200 hover:bg-edge"
            :class="busy ? 'pointer-events-none opacity-50' : ''"
          >
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              class="hidden"
              @change="onBranchFile($event.target.files)"
            />
            {{ busy ? 'Uploading…' : '+ Fix / branch here' }}
          </label>
          <button
            v-if="canApprove && !isApproved(selectedNode)"
            type="button"
            :disabled="busy"
            class="flex-1 rounded-md border border-teal-400/60 px-2 py-1 text-[11px] text-teal-200 hover:bg-teal-400/10 disabled:opacity-50"
            @click="approveSelected"
          >
            Approve
          </button>
          <button
            v-if="isDraft(selectedNode) && !isApproved(selectedNode) && canFix"
            type="button"
            :disabled="busy"
            class="flex-1 rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-300 hover:bg-edge disabled:opacity-50"
            @click="discardSelected"
          >
            Discard draft
          </button>
        </div>
      </div>
    </aside>
  </div>
</template>
