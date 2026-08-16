<script>
/**
 * PROTOTYPE — throwaway. Not wired to the API, not tested, delete when the
 * question is settled.
 *
 * Question: what should the slot's variant/version view look like, given that
 * versions can branch (v1 -> v1.1 AND v1.2), and given we have not decided
 * whether a top-level branch is a rival attempt (pick one) or a deliverable
 * (ship several).
 *
 * Three takes, switchable in the bar at the bottom. The approval-model switch is
 * there too, because the right layout depends on which model is real.
 */

const APPROVER = 'Ola Owner'

/** Natural aspect per top-level branch — children inherit it. */
const RATIOS = { a: 16 / 9, b: 1, c: 9 / 16 }

function seed() {
  return {
    name: 'Hero banner — autumn',
    nodes: [
      { id: 'a', parent: null, label: '16x9', v: 'v1',
        who: 'Maya', when: '14 Aug', open: 3, status: 'done', tone: '#8a5a3b' },
      { id: 'b', parent: null, label: '1x1', v: 'v1',
        who: 'Maya', when: '14 Aug', open: 0, status: 'done', tone: '#3b5a8a' },
      { id: 'c', parent: null, label: '9x16', v: 'v1',
        who: 'Leo', when: '15 Aug', open: 0, status: 'scanning', tone: '#3b7a5a' },
      // 'a' forks: two competing fixes of the same version.
      { id: 'a1', parent: 'a', label: '', v: 'v2',
        who: 'Leo', when: '15 Aug', open: 0, status: 'done', tone: '#9a6a45' },
      { id: 'a2', parent: 'a', label: '', v: 'v2 alt',
        who: 'Maya', when: '15 Aug', open: 1, status: 'done', tone: '#7a4a2b' },
      { id: 'a1a', parent: 'a1', label: '', v: 'v3',
        who: 'Leo', when: '16 Aug', open: 0, status: 'done', tone: '#aa7a55' },
      { id: 'b1', parent: 'b', label: '', v: 'v2',
        who: 'Sari', when: '15 Aug', open: 0, status: 'done', tone: '#4b6a9a' },
    ],
    approved: ['a1a'],
  }
}

const NODE_W = 176
const LANE_W = 216
const ROW_H = 104

export default {
  name: 'PrototypeSlotFlowPage',
  data() {
    return {
      // On the instance, not module scope: a template cannot see module
      // constants, and referencing one silently yields undefined — which is how
      // every node ended up positioned at NaN and stacked in one pile.
      NODE_W,
      LANE_W,
      ROW_H,
      APPROVER,
      slot: seed(),
      model: 'perBranch',
      selected: 'a1a',
      hovered: null,
      hoverBox: null,
      log: [],
    }
  },
  computed: {
    variant() {
      return String(this.$route.query.v || '2')
    },
    byId() {
      return Object.fromEntries(this.slot.nodes.map((n) => [n.id, n]))
    },
    childrenOf() {
      const map = {}
      for (const n of this.slot.nodes) (map[n.parent] ??= []).push(n)
      return map
    },
    roots() {
      return this.childrenOf[null] || []
    },
    rows() {
      return this.outline()
    },
    layout() {
      const rows = this.rows
      const leaves = rows.filter((r) => !(this.childrenOf[r.node.id] || []).length)
      const lane = {}
      leaves.forEach((leaf, index) => {
        let cur = leaf.node
        while (cur) {
          if (lane[cur.id] === undefined) lane[cur.id] = index
          cur = cur.parent ? this.byId[cur.parent] : null
        }
      })
      const rowIndex = Object.fromEntries(rows.map((r, i) => [r.node.id, i]))
      return {
        lane,
        rowIndex,
        width: leaves.length * LANE_W,
        height: rows.length * ROW_H + 24,
      }
    },
    winningPaths() {
      return this.slot.approved.map((id) => {
        const path = []
        let cur = this.byId[id]
        while (cur) {
          path.push(cur.id)
          cur = cur.parent ? this.byId[cur.parent] : null
        }
        return path
      })
    },
    onWinningPath() {
      return new Set(this.winningPaths.flat())
    },
    rootOfApproved() {
      return new Set(this.winningPaths.map((p) => p[p.length - 1]))
    },
    /** Where the floating preview sits: beside the node, clamped to the viewport. */
    previewStyle() {
      if (!this.hoverBox) return { display: 'none' }
      const node = this.byId[this.hovered]
      const width = 300
      const height = Math.round(width / this.ratioOf(node)) + 74
      const spaceRight = window.innerWidth - this.hoverBox.right
      const left =
        spaceRight > width + 32 ? this.hoverBox.right + 16 : this.hoverBox.left - width - 16
      const top = Math.min(
        Math.max(12, this.hoverBox.top + this.hoverBox.height / 2 - height / 2),
        window.innerHeight - height - 90,
      )
      return { left: `${Math.max(12, left)}px`, top: `${top}px`, width: `${width}px` }
    },
  },
  methods: {
    setVariant(v) {
      this.$router.replace({ query: { ...this.$route.query, v } })
    },
    rootOf(node) {
      let cur = node
      while (cur.parent) cur = this.byId[cur.parent]
      return cur
    },
    ratioOf(node) {
      return RATIOS[this.rootOf(node).id] || 1
    },
    isApproved(node) {
      return this.slot.approved.includes(node.id)
    },
    isArchived(node) {
      if (!this.slot.approved.length) return false
      if (this.model === 'single') return !this.onWinningPath.has(node.id)
      const root = this.rootOf(node).id
      if (!this.rootOfApproved.has(root)) return false
      return !this.onWinningPath.has(node.id)
    },
    statusOf(node) {
      if (this.isApproved(node)) return { label: 'Approved', dot: '#5eead4' }
      if (node.status !== 'done') return { label: 'Reviewing…', dot: '#c4c4cc' }
      if (node.open) return { label: `${node.open} open`, dot: '#fbbf24' }
      return { label: 'Clean', dot: '#5eead4' }
    },
    onEnter(node, event) {
      this.hovered = node.id
      this.hoverBox = event.currentTarget.getBoundingClientRect()
    },
    onLeave() {
      this.hovered = null
      this.hoverBox = null
    },
    approve(node) {
      if (this.model === 'single') this.slot.approved = [node.id]
      else {
        const root = this.rootOf(node).id
        this.slot.approved = this.slot.approved.filter(
          (id) => this.rootOf(this.byId[id]).id !== root,
        )
        this.slot.approved.push(node.id)
      }
      this.note(`approved ${this.pathLabel(node)}`)
    },
    unapprove(node) {
      this.slot.approved = this.slot.approved.filter((id) => id !== node.id)
      this.note(`un-approved ${this.pathLabel(node)}`)
    },
    branch(node) {
      const id = `${node.id}x${(this.childrenOf[node.id] || []).length + 1}`
      this.slot.nodes.push({
        id, parent: node.id, label: '', v: 'new',
        who: 'You', when: 'now', open: 0, status: 'scanning', tone: '#5a5a6a',
      })
      this.selected = id
      this.note(`branched a new attempt from ${this.pathLabel(node)}`)
    },
    pathLabel(node) {
      const root = this.rootOf(node)
      return root.id === node.id ? root.label : `${root.label} ${node.v}`
    },
    note(text) {
      this.log.unshift(text)
      this.log = this.log.slice(0, 5)
    },
    reset() {
      this.slot = seed()
      this.selected = 'a1a'
      this.log = []
    },
    outline(parent = null, depth = 0, acc = []) {
      for (const child of this.childrenOf[parent] || []) {
        acc.push({ node: child, depth })
        this.outline(child.id, depth + 1, acc)
      }
      return acc
    },
    rowsFor(rootId) {
      return this.rows.filter((r) => this.rootOf(r.node).id === rootId)
    },
  },
}
</script>

<template>
  <!-- Grid + vignette give the canvas depth so the cards read as floating on it -->
  <div class="relative min-h-screen pb-32">
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
      style="background: radial-gradient(ellipse at 50% 38%, transparent 20%, rgba(6, 6, 8, 0.82) 78%)"
    />

    <div class="relative mx-auto max-w-6xl px-6 py-8 text-center">
      <p
        class="mb-2 inline-block rounded-full border border-warning/40 bg-warning/10 px-2.5 py-0.5 text-[11px] text-warning"
      >
        PROTOTYPE — fake data, nothing is saved
      </p>
      <h2 class="text-2xl font-medium tracking-tight text-neutral-50">{{ slot.name }}</h2>
      <p class="mt-1 text-xs text-neutral-400">
        {{ roots.length }} top-level branches · {{ slot.nodes.length }} nodes ·
        {{ slot.approved.length }} approved
      </p>
    </div>

    <!-- ═══ TAKE 1 — top-down org chart ═══ -->
    <div v-if="variant === '1'" class="relative overflow-x-auto px-6">
      <div class="mx-auto flex w-max justify-center gap-12">
        <div v-for="root in roots" :key="root.id" class="flex flex-col items-center">
          <div class="mb-2 text-[11px] uppercase tracking-widest text-neutral-400">
            {{ root.label }}
          </div>
          <div
            v-for="row in rowsFor(root.id)"
            :key="row.node.id"
            class="flex flex-col items-center"
          >
            <div v-if="row.depth" class="h-7 w-px bg-neutral-700" />
            <button
              type="button"
              class="rounded-xl border p-2.5 text-left shadow-xl shadow-black/50 transition duration-150"
              :style="{ width: `${NODE_W}px` }"
              :class="[
                isApproved(row.node)
                  ? 'border-teal-400/70 bg-teal-400/10 shadow-teal-500/10'
                  : 'border-edge-strong bg-panel-2 hover:border-neutral-500',
                isArchived(row.node) ? 'opacity-45 saturate-50' : '',
                selected === row.node.id ? 'ring-2 ring-neutral-300' : '',
                hovered === row.node.id ? '-translate-y-0.5' : '',
              ]"
              @click="selected = row.node.id"
              @mouseenter="onEnter(row.node, $event)"
              @mouseleave="onLeave"
            >
              <div
                class="mb-2 w-full rounded-md ring-1 ring-inset ring-white/10"
                :style="{ background: row.node.tone, aspectRatio: ratioOf(row.node) }"
              />
              <div class="flex items-center gap-1.5">
                <span class="font-mono text-xs text-neutral-100">{{ row.node.v }}</span>
                <span class="ml-auto flex items-center gap-1 text-[10px] text-neutral-300">
                  <span
                    class="size-1.5 rounded-full"
                    :style="{ background: statusOf(row.node).dot }"
                  />
                  {{ statusOf(row.node).label }}
                </span>
              </div>
              <div class="text-[11px] text-neutral-400">
                {{ row.node.who }} · {{ row.node.when }}
              </div>
              <div v-if="isApproved(row.node)" class="mt-2">
                <div class="mb-1 text-[10px] text-teal-300">✓ {{ APPROVER }}</div>
                <span
                  class="block rounded-md bg-neutral-50 px-2 py-1 text-center text-[10px] font-medium text-neutral-900"
                >
                  Download original
                </span>
              </div>
            </button>
          </div>
        </div>
      </div>
      <p class="mx-auto mt-6 max-w-xl text-center text-[11px] text-neutral-400">
        Take 1 — a column per top-level branch. Simple, but a fork renders as a flat stack: you
        cannot see that v2 and v2 alt are rivals.
      </p>
    </div>

    <!-- ═══ TAKE 2 — lane graph with real connectors ═══ -->
    <div v-else-if="variant === '2'" class="relative overflow-x-auto px-6">
      <div class="mx-auto w-max">
        <div
          class="relative"
          :style="{ width: `${layout.width}px`, height: `${layout.height}px` }"
        >
          <svg class="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
            <path
              v-for="row in rows.filter((r) => r.node.parent)"
              :key="`e-${row.node.id}`"
              :d="`M ${layout.lane[row.node.parent] * LANE_W + NODE_W / 2} ${layout.rowIndex[row.node.parent] * ROW_H + 84}
                   C ${layout.lane[row.node.parent] * LANE_W + NODE_W / 2} ${layout.rowIndex[row.node.id] * ROW_H - 4},
                     ${layout.lane[row.node.id] * LANE_W + NODE_W / 2} ${layout.rowIndex[row.node.parent] * ROW_H + 104},
                     ${layout.lane[row.node.id] * LANE_W + NODE_W / 2} ${layout.rowIndex[row.node.id] * ROW_H + 4}`"
              fill="none"
              :stroke="onWinningPath.has(row.node.id) ? '#2dd4bf' : '#3f3f46'"
              :stroke-width="onWinningPath.has(row.node.id) ? 2 : 1.5"
              :opacity="isArchived(row.node) ? 0.35 : 1"
            />
          </svg>

          <button
            v-for="row in rows"
            :key="row.node.id"
            type="button"
            class="absolute rounded-xl border p-2.5 text-left shadow-xl shadow-black/50 transition duration-150"
            :style="{
              width: `${NODE_W}px`,
              left: `${layout.lane[row.node.id] * LANE_W}px`,
              top: `${layout.rowIndex[row.node.id] * ROW_H + 4}px`,
            }"
            :class="[
              isApproved(row.node)
                ? 'border-teal-400/70 bg-teal-400/10 shadow-teal-500/10'
                : 'border-edge-strong bg-panel-2 hover:border-neutral-500',
              isArchived(row.node) ? 'opacity-45 saturate-50' : '',
              selected === row.node.id ? 'ring-2 ring-neutral-300' : '',
              hovered === row.node.id ? 'z-10 -translate-y-0.5' : '',
            ]"
            @click="selected = row.node.id"
            @mouseenter="onEnter(row.node, $event)"
            @mouseleave="onLeave"
          >
            <div class="flex items-center gap-2.5">
              <div
                class="h-10 w-14 shrink-0 rounded ring-1 ring-inset ring-white/10"
                :style="{ background: row.node.tone }"
              />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="font-mono text-xs text-neutral-100">{{ row.node.v }}</span>
                  <span
                    v-if="row.node.label"
                    class="rounded-full border border-neutral-600 px-1.5 text-[9px] text-neutral-300"
                  >{{ row.node.label }}</span>
                </div>
                <div class="truncate text-[11px] text-neutral-400">
                  {{ row.node.who }} · {{ row.node.when }}
                </div>
              </div>
            </div>
            <div class="mt-2 flex items-center gap-1.5 text-[10px] text-neutral-300">
              <span class="size-1.5 rounded-full" :style="{ background: statusOf(row.node).dot }" />
              {{ statusOf(row.node).label }}
              <span
                v-if="isApproved(row.node)"
                class="ml-auto rounded bg-neutral-50 px-1.5 py-0.5 text-[9px] font-medium text-neutral-900"
              >Download</span>
            </div>
          </button>
        </div>
      </div>
      <p class="mx-auto mt-6 max-w-xl text-center text-[11px] text-neutral-400">
        Take 2 — git-graph lanes. A fork is unmistakable: two curves leaving one node. The winning
        path is drawn in teal.
      </p>
    </div>

    <!-- ═══ TAKE 3 — indented outline ═══ -->
    <div v-else class="relative mx-auto max-w-2xl space-y-1.5 px-6">
      <div
        v-for="row in rows"
        :key="row.node.id"
        class="flex items-center gap-3 rounded-xl border p-2.5 shadow-lg shadow-black/40 transition"
        :class="[
          isApproved(row.node)
            ? 'border-teal-400/70 bg-teal-400/10'
            : 'border-edge-strong bg-panel-2 hover:border-neutral-500',
          isArchived(row.node) ? 'opacity-45 saturate-50' : '',
          selected === row.node.id ? 'ring-2 ring-neutral-300' : '',
        ]"
        :style="{ marginLeft: `${row.depth * 30}px` }"
        @click="selected = row.node.id"
        @mouseenter="onEnter(row.node, $event)"
        @mouseleave="onLeave"
      >
        <span v-if="row.depth" class="-ml-5 text-neutral-600">└</span>
        <div
          class="h-11 w-14 shrink-0 rounded ring-1 ring-inset ring-white/10"
          :style="{ background: row.node.tone }"
        />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-mono text-xs text-neutral-100">{{ row.node.v }}</span>
            <span
              v-if="row.node.label"
              class="rounded-full border border-neutral-600 px-1.5 text-[10px] text-neutral-300"
            >{{ row.node.label }}</span>
          </div>
          <div class="text-[11px] text-neutral-400">{{ row.node.who }} · {{ row.node.when }}</div>
        </div>
        <span class="ml-auto flex items-center gap-1.5 text-[11px] text-neutral-300">
          <span class="size-1.5 rounded-full" :style="{ background: statusOf(row.node).dot }" />
          {{ statusOf(row.node).label }}
        </span>
        <span
          v-if="isApproved(row.node)"
          class="rounded bg-neutral-50 px-2 py-1 text-[10px] font-medium text-neutral-900"
        >Download</span>
      </div>
      <p class="mt-6 text-center text-[11px] text-neutral-400">
        Take 3 — indented outline. Densest and never scrolls sideways, but branching reads as
        nesting rather than as rivalry.
      </p>
    </div>

    <!-- hover preview: the asset at its natural aspect, uncropped -->
    <div
      v-if="hovered && byId[hovered]"
      class="pointer-events-none fixed z-40 rounded-xl border border-neutral-600 bg-panel-2 p-2 shadow-2xl shadow-black/70"
      :style="previewStyle"
    >
      <div
        class="w-full rounded-md ring-1 ring-inset ring-white/10"
        :style="{ background: byId[hovered].tone, aspectRatio: ratioOf(byId[hovered]) }"
      />
      <div class="mt-2 flex items-baseline gap-2 px-0.5">
        <span class="font-mono text-xs text-neutral-100">{{ byId[hovered].v }}</span>
        <span class="text-[11px] text-neutral-400">
          {{ rootOf(byId[hovered]).label }} · {{ byId[hovered].who }}
        </span>
        <span class="ml-auto text-[11px] text-neutral-400">{{ byId[hovered].when }}</span>
      </div>
    </div>

    <!-- selected node actions -->
    <div
      v-if="byId[selected]"
      class="relative mx-auto mt-10 max-w-2xl rounded-xl border border-edge-strong bg-panel-2/80 p-3 shadow-xl shadow-black/40"
    >
      <div class="flex flex-wrap items-center justify-center gap-2">
        <span class="text-xs text-neutral-200">
          Selected <span class="font-mono text-neutral-50">{{ pathLabel(byId[selected]) }}</span>
        </span>
        <button
          type="button"
          class="rounded-md border border-neutral-600 px-2.5 py-1 text-[11px] text-neutral-200 hover:bg-edge"
          @click="branch(byId[selected])"
        >
          + branch an attempt here
        </button>
        <button
          v-if="!isApproved(byId[selected])"
          type="button"
          class="rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900 hover:bg-white"
          @click="approve(byId[selected])"
        >
          Approve
        </button>
        <button
          v-else
          type="button"
          class="rounded-md border border-neutral-600 px-2.5 py-1 text-[11px] text-neutral-200 hover:bg-edge"
          @click="unapprove(byId[selected])"
        >
          Un-approve
        </button>
      </div>
      <ul v-if="log.length" class="mt-2 space-y-0.5 text-center">
        <li v-for="(line, index) in log" :key="index" class="text-[11px] text-neutral-500">
          {{ line }}
        </li>
      </ul>
    </div>

    <!-- floating switcher -->
    <div
      class="fixed inset-x-0 bottom-0 z-30 border-t border-edge-strong bg-ink/90 px-6 py-3 backdrop-blur"
    >
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-3">
        <span class="text-[11px] uppercase tracking-widest text-neutral-400">Layout</span>
        <div class="flex gap-1">
          <button
            v-for="option in [
              { id: '1', label: 'Org chart' },
              { id: '2', label: 'Lane graph' },
              { id: '3', label: 'Outline' },
            ]"
            :key="option.id"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition"
            :class="
              variant === option.id
                ? 'bg-neutral-50 font-medium text-neutral-900'
                : 'text-neutral-300 hover:bg-edge hover:text-neutral-50'
            "
            @click="setVariant(option.id)"
          >
            {{ option.label }}
          </button>
        </div>

        <span class="ml-5 text-[11px] uppercase tracking-widest text-neutral-400">Approval</span>
        <div class="flex gap-1">
          <button
            v-for="option in [
              { id: 'single', label: 'One winner per slot' },
              { id: 'perBranch', label: 'One per deliverable' },
            ]"
            :key="option.id"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition"
            :class="
              model === option.id
                ? 'bg-neutral-50 font-medium text-neutral-900'
                : 'text-neutral-300 hover:bg-edge hover:text-neutral-50'
            "
            @click="model = option.id"
          >
            {{ option.label }}
          </button>
        </div>

        <button
          type="button"
          class="ml-4 text-[11px] text-neutral-400 hover:text-neutral-100"
          @click="reset"
        >
          Reset
        </button>
      </div>
    </div>
  </div>
</template>
