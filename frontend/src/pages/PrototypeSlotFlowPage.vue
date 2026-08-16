<script>
/**
 * PROTOTYPE — throwaway. Not wired to the API, not tested, delete when the
 * question is settled.
 *
 * Question it answers: what should the slot's variant/version view look like,
 * given that versions can branch (v1 -> v1.1 AND v1.2), and given we have not
 * decided whether a variant is a rival attempt (pick one) or a deliverable
 * (ship several).
 *
 * Three radically different takes on the same fake slot, switchable in the bar
 * at the bottom. The approval-model switch is in there too, because the right
 * layout probably depends on which model is real.
 */

const APPROVER = 'Ola Owner'

/** One fake slot. Node 'a1' branches into two children — the case that matters. */
function seed() {
  return {
    name: 'Hero banner — autumn',
    nodes: [
      // Level 1: children of the slot itself = "variants"
      { id: 'a', parent: null, label: '16x9', kind: 'deliverable', v: 'v1',
        who: 'Maya', when: '14 Aug', open: 3, status: 'done', tone: '#8a5a3b' },
      { id: 'b', parent: null, label: '1x1', kind: 'deliverable', v: 'v1',
        who: 'Maya', when: '14 Aug', open: 0, status: 'done', tone: '#3b5a8a' },
      { id: 'c', parent: null, label: '9x16', kind: 'deliverable', v: 'v1',
        who: 'Leo', when: '15 Aug', open: 0, status: 'scanning', tone: '#3b7a5a' },

      // Level 2+: fixes. 'a' forks into two competing fixes.
      { id: 'a1', parent: 'a', label: '', kind: 'fix', v: 'v2',
        who: 'Leo', when: '15 Aug', open: 0, status: 'done', tone: '#9a6a45' },
      { id: 'a2', parent: 'a', label: '', kind: 'fix', v: 'v2 alt',
        who: 'Maya', when: '15 Aug', open: 1, status: 'done', tone: '#7a4a2b' },
      { id: 'a1a', parent: 'a1', label: '', kind: 'fix', v: 'v3',
        who: 'Leo', when: '16 Aug', open: 0, status: 'done', tone: '#aa7a55' },
      { id: 'b1', parent: 'b', label: '', kind: 'fix', v: 'v2',
        who: 'Sari', when: '15 Aug', open: 0, status: 'done', tone: '#4b6a9a' },
    ],
    approved: ['a1a'],
  }
}

export default {
  name: 'PrototypeSlotFlowPage',
  data() {
    return {
      slot: seed(),
      // 'single' = one winner per slot, rest archived.
      // 'perBranch' = one winner per top-level deliverable, several ship.
      model: 'perBranch',
      selected: 'a1a',
      log: [],
    }
  },
  computed: {
    variant() {
      return String(this.$route.query.v || '1')
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
    /** Nodes on the path from an approved node up to its root, per approval. */
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
    isApproved(node) {
      return this.slot.approved.includes(node.id)
    },
    /** Dimmed = lost. Depends on the model, which is the point of the switch. */
    isArchived(node) {
      if (!this.slot.approved.length) return false
      if (this.model === 'single') return !this.onWinningPath.has(node.id)
      const root = this.rootOf(node).id
      if (!this.rootOfApproved.has(root)) return false
      return !this.onWinningPath.has(node.id)
    },
    statusOf(node) {
      if (this.isApproved(node)) return { label: 'Approved', dot: '#9FE1CB' }
      if (node.status !== 'done') return { label: 'Reviewing…', dot: '#a3a3a8' }
      if (node.open) return { label: `${node.open} open`, dot: '#FAC775' }
      return { label: 'Clean', dot: '#9FE1CB' }
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
        id, parent: node.id, label: '', kind: 'fix', v: 'new',
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
      this.log = this.log.slice(0, 6)
    },
    reset() {
      this.slot = seed()
      this.selected = 'a1a'
      this.log = []
    },
    depthOf(node) {
      let d = 0
      let cur = node
      while (cur.parent) { cur = this.byId[cur.parent]; d += 1 }
      return d
    },
    /** Flatten to rows for the outline take. */
    outline(node = null, depth = 0, acc = []) {
      for (const child of this.childrenOf[node] || []) {
        acc.push({ node: child, depth })
        this.outline(child.id, depth + 1, acc)
      }
      return acc
    },
    /** Column layout for the graph takes: each leaf gets a lane. */
    lanes() {
      const rows = this.outline()
      const leaves = rows.filter((r) => !(this.childrenOf[r.node.id] || []).length)
      const lane = {}
      leaves.forEach((leaf, index) => {
        let cur = leaf.node
        while (cur) {
          if (lane[cur.id] === undefined) lane[cur.id] = index
          cur = cur.parent ? this.byId[cur.parent] : null
        }
      })
      return { rows, lane, laneCount: leaves.length }
    },
  },
}
</script>

<template>
  <div class="min-h-screen pb-28">
    <div class="mx-auto max-w-6xl px-6 py-6">
      <p class="mb-1 inline-block rounded bg-warning/15 px-2 py-0.5 text-[11px] text-warning">
        PROTOTYPE — fake data, nothing is saved
      </p>
      <h2 class="text-xl font-medium tracking-tight">{{ slot.name }}</h2>
      <p class="mt-1 text-xs text-neutral-500">
        {{ roots.length }} top-level branches · {{ slot.nodes.length }} nodes ·
        {{ slot.approved.length }} approved
      </p>

      <!-- ═══ TAKE 1 — top-down org chart ═══ -->
      <div v-if="variant === '1'" class="mt-8 overflow-x-auto pb-4">
        <div class="flex min-w-max gap-10">
          <div v-for="root in roots" :key="root.id" class="flex flex-col items-center">
            <div class="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">
              {{ root.label }}
            </div>
            <div class="flex flex-col items-center gap-0">
              <template v-for="row in [{ node: root, depth: 0 }]" :key="row.node.id">
                <div />
              </template>
              <!-- recursive render via nested component-less template -->
              <div class="flex flex-col items-center">
                <div
                  v-for="row in outline(null).filter((r) => rootOf(r.node).id === root.id)"
                  :key="row.node.id"
                  class="flex flex-col items-center"
                  :style="{ marginLeft: `${row.depth * 0}px` }"
                >
                  <div v-if="row.depth" class="h-6 w-px bg-edge-strong" />
                  <button
                    type="button"
                    class="w-44 rounded-lg border p-2 text-left transition"
                    :class="[
                      isApproved(row.node)
                        ? 'border-teal-400 bg-teal-400/10'
                        : 'border-edge bg-panel hover:border-edge-strong',
                      isArchived(row.node) ? 'opacity-40' : '',
                      selected === row.node.id ? 'ring-1 ring-neutral-400' : '',
                    ]"
                    @click="selected = row.node.id"
                  >
                    <div
                      class="mb-1.5 h-16 w-full rounded"
                      :style="{ background: row.node.tone }"
                    />
                    <div class="flex items-center gap-1.5">
                      <span class="font-mono text-[11px] text-neutral-300">{{ row.node.v }}</span>
                      <span class="ml-auto flex items-center gap-1 text-[10px] text-neutral-400">
                        <span
                          class="size-1.5 rounded-full"
                          :style="{ background: statusOf(row.node).dot }"
                        />
                        {{ statusOf(row.node).label }}
                      </span>
                    </div>
                    <div class="text-[10px] text-neutral-500">
                      {{ row.node.who }} · {{ row.node.when }}
                    </div>
                    <div v-if="isApproved(row.node)" class="mt-1.5 space-y-1">
                      <div class="text-[10px] text-teal-300">✓ {{ APPROVER }}</div>
                      <span
                        class="block rounded bg-neutral-50 px-2 py-1 text-center text-[10px] font-medium text-neutral-900"
                      >
                        Download original
                      </span>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <p class="mt-3 text-[11px] text-neutral-600">
          Take 1 — one column per top-level branch, fixes stacked below. Simple, but a fork
          renders as a flat stack: you cannot see that v2 and v2 alt are siblings.
        </p>
      </div>

      <!-- ═══ TAKE 2 — lane graph with real connectors ═══ -->
      <div v-else-if="variant === '2'" class="mt-8 overflow-x-auto pb-4">
        <div
          class="relative min-w-max"
          :style="{ height: `${outline().length * 96 + 40}px`, width: `${lanes().laneCount * 200 + 60}px` }"
        >
          <svg class="pointer-events-none absolute inset-0 h-full w-full">
            <line
              v-for="row in outline().filter((r) => r.node.parent)"
              :key="`e-${row.node.id}`"
              :x1="lanes().lane[row.node.parent] * 200 + 88"
              :y1="outline().findIndex((r2) => r2.node.id === row.node.parent) * 96 + 74"
              :x2="lanes().lane[row.node.id] * 200 + 88"
              :y2="outline().findIndex((r2) => r2.node.id === row.node.id) * 96 + 12"
              stroke="#2e2e33"
              stroke-width="2"
            />
          </svg>
          <button
            v-for="(row, index) in outline()"
            :key="row.node.id"
            type="button"
            class="absolute w-44 rounded-lg border p-2 text-left transition"
            :class="[
              isApproved(row.node)
                ? 'border-teal-400 bg-teal-400/10'
                : 'border-edge bg-panel hover:border-edge-strong',
              isArchived(row.node) ? 'opacity-40' : '',
              selected === row.node.id ? 'ring-1 ring-neutral-400' : '',
            ]"
            :style="{ left: `${lanes().lane[row.node.id] * 200}px`, top: `${index * 96 + 12}px` }"
            @click="selected = row.node.id"
          >
            <div class="flex items-center gap-2">
              <div class="size-9 shrink-0 rounded" :style="{ background: row.node.tone }" />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="font-mono text-[11px] text-neutral-200">{{ row.node.v }}</span>
                  <span
                    v-if="row.node.label"
                    class="rounded-full border border-edge-strong px-1.5 text-[9px] text-neutral-400"
                  >{{ row.node.label }}</span>
                </div>
                <div class="truncate text-[10px] text-neutral-500">
                  {{ row.node.who }} · {{ row.node.when }}
                </div>
              </div>
            </div>
            <div class="mt-1.5 flex items-center gap-1 text-[10px] text-neutral-400">
              <span class="size-1.5 rounded-full" :style="{ background: statusOf(row.node).dot }" />
              {{ statusOf(row.node).label }}
              <span
                v-if="isApproved(row.node)"
                class="ml-auto rounded bg-neutral-50 px-1.5 text-[9px] font-medium text-neutral-900"
              >Download</span>
            </div>
          </button>
        </div>
        <p class="mt-3 text-[11px] text-neutral-600">
          Take 2 — git-graph lanes. A fork is unmistakable: two lines leaving one node. Scales to
          deep chains, but a wide slot scrolls sideways.
        </p>
      </div>

      <!-- ═══ TAKE 3 — indented outline, no graph ═══ -->
      <div v-else class="mt-8 space-y-1">
        <div
          v-for="row in outline()"
          :key="row.node.id"
          class="flex items-center gap-3 rounded-lg border p-2 transition"
          :class="[
            isApproved(row.node) ? 'border-teal-400 bg-teal-400/10' : 'border-edge bg-panel',
            isArchived(row.node) ? 'opacity-40' : '',
            selected === row.node.id ? 'ring-1 ring-neutral-400' : '',
          ]"
          :style="{ marginLeft: `${row.depth * 28}px` }"
          @click="selected = row.node.id"
        >
          <span v-if="row.depth" class="-ml-4 text-neutral-700">└</span>
          <div class="size-10 shrink-0 rounded" :style="{ background: row.node.tone }" />
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-mono text-xs text-neutral-200">{{ row.node.v }}</span>
              <span
                v-if="row.node.label"
                class="rounded-full border border-edge-strong px-1.5 text-[10px] text-neutral-400"
              >{{ row.node.label }}</span>
            </div>
            <div class="text-[11px] text-neutral-500">{{ row.node.who }} · {{ row.node.when }}</div>
          </div>
          <span class="ml-auto flex items-center gap-1.5 text-[11px] text-neutral-400">
            <span class="size-1.5 rounded-full" :style="{ background: statusOf(row.node).dot }" />
            {{ statusOf(row.node).label }}
          </span>
          <span
            v-if="isApproved(row.node)"
            class="rounded bg-neutral-50 px-2 py-1 text-[10px] font-medium text-neutral-900"
          >Download</span>
        </div>
        <p class="mt-3 text-[11px] text-neutral-600">
          Take 3 — indented outline, no SVG. Densest and never scrolls sideways, but branching
          reads as nesting rather than as rivalry.
        </p>
      </div>

      <!-- selected node actions -->
      <div v-if="byId[selected]" class="mt-8 rounded-lg border border-edge bg-panel p-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs text-neutral-300">
            Selected: <span class="font-mono">{{ pathLabel(byId[selected]) }}</span>
          </span>
          <button
            type="button"
            class="rounded border border-edge-strong px-2 py-1 text-[11px] text-neutral-300 hover:bg-edge"
            @click="branch(byId[selected])"
          >
            + branch an attempt from here
          </button>
          <button
            v-if="!isApproved(byId[selected])"
            type="button"
            class="rounded bg-neutral-50 px-2 py-1 text-[11px] font-medium text-neutral-900"
            @click="approve(byId[selected])"
          >
            Approve this
          </button>
          <button
            v-else
            type="button"
            class="rounded border border-edge-strong px-2 py-1 text-[11px] text-neutral-300 hover:bg-edge"
            @click="unapprove(byId[selected])"
          >
            Un-approve
          </button>
        </div>
        <ul class="mt-2 space-y-0.5">
          <li v-for="(line, index) in log" :key="index" class="text-[11px] text-neutral-600">
            {{ line }}
          </li>
        </ul>
      </div>
    </div>

    <!-- floating switcher -->
    <div
      class="fixed inset-x-0 bottom-0 border-t border-edge-strong bg-panel-2/95 px-6 py-3 backdrop-blur"
    >
      <div class="mx-auto flex max-w-6xl flex-wrap items-center gap-4">
        <span class="text-[11px] uppercase tracking-wide text-neutral-500">Layout</span>
        <div class="flex gap-1">
          <button
            v-for="option in [
              { id: '1', label: '1 · Org chart' },
              { id: '2', label: '2 · Lane graph' },
              { id: '3', label: '3 · Outline' },
            ]"
            :key="option.id"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition"
            :class="
              variant === option.id
                ? 'bg-neutral-50 font-medium text-neutral-900'
                : 'text-neutral-400 hover:bg-edge hover:text-neutral-100'
            "
            @click="setVariant(option.id)"
          >
            {{ option.label }}
          </button>
        </div>

        <span class="ml-4 text-[11px] uppercase tracking-wide text-neutral-500">Approval</span>
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
                : 'text-neutral-400 hover:bg-edge hover:text-neutral-100'
            "
            @click="model = option.id"
          >
            {{ option.label }}
          </button>
        </div>

        <button
          type="button"
          class="ml-auto text-[11px] text-neutral-500 hover:text-neutral-200"
          @click="reset"
        >
          Reset
        </button>
      </div>
    </div>
  </div>
</template>
