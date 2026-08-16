<script>
/**
 * PROTOTYPE — throwaway. Not wired to the API, not tested.
 *
 * Question: what should the slot's variant/version view look like, given that
 * versions can branch, and given we have not decided whether a top-level branch
 * is a rival attempt (pick one) or a deliverable (ship several).
 */

const APPROVER = 'Ola Owner'
const RATIOS = { a: 16 / 9, b: 1, c: 9 / 16 }

const NODE_W = 168
const COL_W = 196
const ROW_H = 132

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

/** Fake threads so the sidebar has something to be. Keyed by node id. */
function seedChats() {
  return {
    a: [
      { from: 'agent', body: 'Three findings on this version: six fingers on the left hand, a warped logo edge, and an illegible strapline.' },
      { from: 'you', body: 'Which of those blocks publish?' },
      { from: 'agent', body: 'The hand. The other two are warnings — they would not stop a release on their own.' },
    ],
    a1a: [
      { from: 'agent', body: 'All three findings from v1 are resolved in this version. Nothing new was raised.' },
    ],
    a2: [
      { from: 'agent', body: 'The strapline is still illegible here. The hand was fixed, but this branch did not address the logo.' },
    ],
  }
}

export default {
  name: 'PrototypeSlotFlowPage',
  data() {
    return {
      NODE_W, COL_W, ROW_H, APPROVER,
      slot: seed(),
      chats: seedChats(),
      model: 'perBranch',
      selected: 'a1a',
      hovered: null,
      hoverBox: null,
      draft: '',
    }
  },
  computed: {
    view() {
      return String(this.$route.query.v || 'tree')
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
    /**
     * Classic tree layout: leaves take the next free column, every parent centres
     * over its children. That is what puts the slot at the top with everything
     * hanging beneath it, so the starting point needs no explaining.
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
    summary() {
      const open = this.slot.nodes.reduce((total, n) => total + n.open, 0)
      return `${this.roots.length} branches · ${this.slot.nodes.length} versions · ${this.slot.approved.length} approved · ${open} open`
    },
    thread() {
      return this.chats[this.selected] || []
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
        window.innerHeight - height - 84,
      )
      return { left: `${left}px`, top: `${top}px`, width: `${width}px` }
    },
  },
  methods: {
    setView(v) {
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
    edge(node) {
      const l = this.layout
      const parentCol = node.parent === null ? l.rootColumn : l.column[node.parent]
      const parentDepth = node.parent === null ? 0 : l.depth[node.parent]
      const x1 = parentCol * this.COL_W + this.NODE_W / 2
      const y1 = parentDepth * this.ROW_H + (node.parent === null ? 62 : 96)
      const x2 = l.column[node.id] * this.COL_W + this.NODE_W / 2
      const y2 = l.depth[node.id] * this.ROW_H + 4
      const mid = (y1 + y2) / 2
      return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`
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
    },
    unapprove(node) {
      this.slot.approved = this.slot.approved.filter((id) => id !== node.id)
    },
    branch(node) {
      const id = `${node.id}x${(this.childrenOf[node.id] || []).length + 1}`
      this.slot.nodes.push({
        id, parent: node.id, label: '', v: 'new',
        who: 'You', when: 'now', open: 0, status: 'scanning', tone: '#5a5a6a',
      })
      this.selected = id
    },
    pathLabel(node) {
      const root = this.rootOf(node)
      return root.id === node.id ? root.label : `${root.label} ${node.v}`
    },
    send() {
      const body = this.draft.trim()
      if (!body) return
      const thread = (this.chats[this.selected] ??= [])
      thread.push({ from: 'you', body })
      this.draft = ''
      const node = this.byId[this.selected]
      this.$nextTick(() => {
        thread.push({
          from: 'agent',
          body: `Looking at ${this.pathLabel(node)} — ${
            node.open
              ? `${node.open} finding(s) still open here.`
              : 'nothing is outstanding on this version.'
          } (prototype reply)`,
        })
      })
    },
    reset() {
      this.slot = seed()
      this.chats = seedChats()
      this.selected = 'a1a'
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
  <div class="relative min-h-screen">
    <!-- canvas: grid + vignette so the cards read as floating on it -->
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

    <!-- main canvas, room reserved for the chat rail -->
    <div class="relative pb-28 pr-0 xl:pr-[352px]">
      <!-- ═══ TREE ═══ -->
      <div v-if="view === 'tree'" class="overflow-x-auto px-8 pt-10">
        <div class="mx-auto w-max">
          <div
            class="relative"
            :style="{ width: `${layout.width}px`, height: `${layout.height}px` }"
          >
            <svg class="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
              <path
                v-for="root in roots"
                :key="`root-${root.id}`"
                :d="edge(root)"
                fill="none"
                stroke-linecap="round"
                :stroke="onWinningPath.has(root.id) ? '#5eead4' : '#8b8b96'"
                :stroke-width="onWinningPath.has(root.id) ? 2.5 : 2"
                :opacity="isArchived(root) ? 0.7 : 1"
              />
              <path
                v-for="row in rows.filter((r) => r.node.parent)"
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
              <div class="mt-0.5 text-sm font-medium text-neutral-50">{{ slot.name }}</div>
              <div class="mt-1 text-[10px] leading-relaxed text-neutral-400">{{ summary }}</div>
            </div>

            <button
              v-for="row in rows"
              :key="row.node.id"
              type="button"
              class="absolute rounded-xl border p-2.5 text-left shadow-xl shadow-black/50 transition duration-150"
              :style="{
                width: `${NODE_W}px`,
                left: `${layout.column[row.node.id] * COL_W}px`,
                top: `${layout.depth[row.node.id] * ROW_H + 4}px`,
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
                  class="h-9 w-12 shrink-0 rounded ring-1 ring-inset ring-white/10"
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
                <span
                  class="size-1.5 rounded-full"
                  :style="{ background: statusOf(row.node).dot }"
                />
                {{ statusOf(row.node).label }}
                <span
                  v-if="isApproved(row.node)"
                  class="ml-auto rounded bg-neutral-50 px-1.5 py-0.5 text-[9px] font-medium text-neutral-900"
                >Download</span>
              </div>
            </button>
          </div>
        </div>
      </div>

      <!-- ═══ OUTLINE ═══ -->
      <div v-else class="mx-auto max-w-2xl space-y-1.5 px-8 pt-10">
        <div class="mb-3 text-center">
          <div class="text-sm font-medium text-neutral-50">{{ slot.name }}</div>
          <div class="text-[11px] text-neutral-400">{{ summary }}</div>
        </div>
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
          <span v-if="row.depth" class="-ml-5 text-neutral-400">└</span>
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
        </div>
      </div>
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

    <!-- ═══ agent chat rail ═══ -->
    <aside
      class="fixed bottom-0 right-0 top-0 z-20 hidden w-[340px] flex-col border-l border-edge-strong bg-panel/95 backdrop-blur xl:flex"
    >
      <header class="border-b border-edge-strong px-4 py-3">
        <div class="text-[10px] uppercase tracking-widest text-neutral-400">Ask the agent about</div>
        <div v-if="byId[selected]" class="mt-0.5 flex items-center gap-2">
          <div
            class="h-7 w-9 shrink-0 rounded ring-1 ring-inset ring-white/10"
            :style="{ background: byId[selected].tone }"
          />
          <div class="min-w-0">
            <div class="font-mono text-xs text-neutral-50">{{ pathLabel(byId[selected]) }}</div>
            <div class="truncate text-[11px] text-neutral-400">
              {{ byId[selected].who }} · {{ byId[selected].when }} ·
              {{ statusOf(byId[selected]).label }}
            </div>
          </div>
        </div>
      </header>

      <div class="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-4 py-3">
        <p v-if="!thread.length" class="text-[11px] leading-relaxed text-neutral-500">
          Nothing discussed on this version yet. Ask why a finding was raised, what changed since
          the parent, or whether it is safe to approve.
        </p>
        <div
          v-for="(message, index) in thread"
          :key="index"
          class="rounded-lg px-2.5 py-2 text-[12px] leading-relaxed"
          :class="
            message.from === 'agent'
              ? 'bg-panel-2 text-neutral-200'
              : 'ml-6 bg-neutral-50 text-neutral-900'
          "
        >
          <div
            v-if="message.from === 'agent'"
            class="mb-0.5 text-[10px] uppercase tracking-wide text-teal-300"
          >
            QA agent
          </div>
          {{ message.body }}
        </div>
      </div>

      <div class="border-t border-edge-strong p-3">
        <div class="mb-2 flex flex-wrap gap-1.5">
          <button
            v-for="chip in ['What changed since the parent?', 'Safe to approve?', 'Why was this flagged?']"
            :key="chip"
            type="button"
            class="rounded-full border border-neutral-600 px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-edge"
            @click="draft = chip; send()"
          >
            {{ chip }}
          </button>
        </div>
        <div class="flex gap-2">
          <input
            v-model="draft"
            type="text"
            placeholder="Ask about this version…"
            class="min-w-0 flex-1 rounded-md border border-edge-strong bg-panel-2 px-2.5 py-1.5 text-xs text-neutral-100 outline-none focus:border-neutral-500"
            @keyup.enter="send"
          />
          <button
            type="button"
            :disabled="!draft.trim()"
            class="rounded-md bg-neutral-50 px-2.5 py-1.5 text-xs font-medium text-neutral-900 disabled:opacity-40"
            @click="send"
          >
            Send
          </button>
        </div>

        <div v-if="byId[selected]" class="mt-2 flex gap-1.5">
          <button
            type="button"
            class="flex-1 rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-200 hover:bg-edge"
            @click="branch(byId[selected])"
          >
            + branch here
          </button>
          <button
            v-if="!isApproved(byId[selected])"
            type="button"
            class="flex-1 rounded-md bg-neutral-50 px-2 py-1 text-[11px] font-medium text-neutral-900"
            @click="approve(byId[selected])"
          >
            Approve
          </button>
          <button
            v-else
            type="button"
            class="flex-1 rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-200 hover:bg-edge"
            @click="unapprove(byId[selected])"
          >
            Un-approve
          </button>
        </div>
      </div>
    </aside>

    <!-- switcher -->
    <div
      class="fixed bottom-0 left-0 right-0 z-30 border-t border-edge-strong bg-ink/90 px-6 py-2.5 backdrop-blur xl:right-[340px]"
    >
      <div class="flex flex-wrap items-center justify-center gap-3">
        <span class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">
          prototype
        </span>
        <div class="flex gap-1">
          <button
            v-for="option in [
              { id: 'tree', label: 'Tree' },
              { id: 'outline', label: 'Outline' },
            ]"
            :key="option.id"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition"
            :class="
              view === option.id
                ? 'bg-neutral-50 font-medium text-neutral-900'
                : 'text-neutral-300 hover:bg-edge hover:text-neutral-50'
            "
            @click="setView(option.id)"
          >
            {{ option.label }}
          </button>
        </div>

        <span class="ml-3 text-[11px] uppercase tracking-widest text-neutral-400">Approval</span>
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
          class="ml-3 text-[11px] text-neutral-400 hover:text-neutral-100"
          @click="reset"
        >
          Reset
        </button>
      </div>
    </div>
  </div>
</template>
