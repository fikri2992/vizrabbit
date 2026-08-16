<script>
/**
 * PROTOTYPE — throwaway. Not wired to the API, not tested.
 *
 * Question: what does the whole "collaborative partner" app experience feel
 * like — agenda loop, slot specs, verdicts that arrive with remedies,
 * fix-as-branch, the rulebook as case law, share-link approval?
 *
 * Everything is mocked. Interactions that would ingest or generate in the real
 * product run behind staged delays so the pacing is honest.
 */

const WAIT = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function seedSlots() {
  return [
    {
      id: 'hero',
      name: 'Hero banner',
      due: 'Fri 22 Aug',
      spec: [
        { format: '16x9', state: 'approved', tone: '#8a5a3b' },
        { format: '1x1', state: 'ready', tone: '#3b5a8a' },
        { format: '9x16', state: 'missing', tone: '#3b7a5a' },
      ],
    },
    {
      id: 'pdp',
      name: 'Product detail set',
      due: 'Fri 22 Aug',
      spec: [
        { format: '1x1', state: 'in_review', tone: '#6a3b7a' },
        { format: '4x5', state: 'blocked', tone: '#7a3b52' },
      ],
    },
    {
      id: 'story',
      name: 'Story teaser',
      due: 'Mon 25 Aug',
      spec: [{ format: '9x16', state: 'in_review', tone: '#3b6a7a' }],
    },
  ]
}

function seedAgenda() {
  return [
    {
      id: 'absence-916',
      kind: 'absence',
      title: 'Hero banner is missing its 9:16',
      cite: 'spec wants 16x9 · 1x1 · 9:16 — campaign exports Fri 22 Aug',
      action: 'simulate-drive',
      actionLabel: 'Watching Drive — simulate designer drop',
    },
    {
      id: 'stall-pdp',
      kind: 'stall',
      title: '4x5 product shot blocked on Maya',
      cite: 'fix requested 4 days ago · nothing uploaded since',
      action: 'nudge',
      actionLabel: 'Send reminder',
    },
    {
      id: 'ambiguity-r7',
      kind: 'ambiguity',
      title: 'Rule 7 keeps getting overridden — should it change?',
      cite: 'overridden 3 of last 4 citations, every time on lifestyle shots',
      action: 'amend',
      actionLabel: 'Exclude lifestyle shots',
      secondary: 'Keep rule as is',
    },
    {
      id: 'predict-busy',
      kind: 'prediction',
      title: 'New upload will likely trip rule 14',
      cite: 'last 3 busy-background heroes were rejected under rule 14',
      action: 'show-rule',
      actionLabel: 'Show the precedent',
    },
  ]
}

function seedRules() {
  return [
    {
      id: 14,
      text: 'Logo never sits on busy photographic ground',
      born: 'from a dispute on Hero banner v1 · 12 Aug',
      cited: 23,
      overridden: 2,
      trend: [9, 7, 6, 4, 2, 1],
      status: 'healthy',
    },
    {
      id: 7,
      text: 'Product must fill ≥ 60% of frame',
      born: 'ratified from brand PDF extraction · 8 Aug',
      cited: 11,
      overridden: 3,
      trend: [2, 3, 3, 4, 5, 6],
      status: 'contested',
      amended: false,
    },
    {
      id: 3,
      text: 'CTA text contrast ≥ 3:1 against ground',
      born: 'from WCAG baseline, confirmed by Ola · 6 Aug',
      cited: 31,
      overridden: 0,
      trend: [5, 4, 3, 3, 2, 1],
      status: 'healthy',
    },
    {
      id: 9,
      text: 'No drop shadows on packshots',
      born: 'from a dismissal on Spring set · 2 Aug',
      cited: 6,
      overridden: 5,
      trend: [1, 2, 4, 5, 5, 6],
      status: 'dying',
    },
  ]
}

/** The hero slot's 1x1 lineage, the branch the demo grows. */
function seedTree() {
  return [
    { id: 'a', parent: null, label: 'v1', tone: '#3b5a8a', state: 'open', who: 'Maya' },
    { id: 'b', parent: 'a', label: 'v2', tone: '#4b6a9a', state: 'clean', who: 'Maya' },
  ]
}

const GENERATION_STAGES = [
  'Reading the verdict…',
  'Prompting the edit model…',
  'Rendering the candidate…',
  'Registering it as a branch…',
]

export default {
  name: 'PrototypePartnerPage',
  data() {
    return {
      slots: seedSlots(),
      agenda: seedAgenda(),
      rules: seedRules(),
      tree: seedTree(),
      resolved: {}, // agenda id -> outcome line
      toasts: [],
      toastSeq: 0,
      driveState: 'idle', // idle | arriving | reviewing | done
      fixState: 'idle', // idle | generating | rechecking | done
      fixStage: '',
      selectedNode: 'b',
      shareApproved: false,
      shareBusy: false,
      highlightRule: null,
    }
  },
  computed: {
    view() {
      return String(this.$route.query.v || 'today')
    },
    overduePressure() {
      return this.agenda.filter((item) => !this.resolved[item.id]).length
    },
    /** Overall override-rate line: the one health metric, trending down. */
    healthLine() {
      const weeks = [34, 27, 22, 15, 11, 7]
      return this.sparkPath(weeks, 320, 72)
    },
    treeById() {
      return Object.fromEntries(this.tree.map((node) => [node.id, node]))
    },
    node() {
      return this.treeById[this.selectedNode]
    },
    kindMeta() {
      return {
        absence: { label: 'Missing', tone: '#FAC775' },
        stall: { label: 'Stalled', tone: '#F09595' },
        ambiguity: { label: 'Your precedent disagrees with itself', tone: '#c4b5fd' },
        prediction: { label: 'Heads up', tone: '#93c5fd' },
        pickable: { label: 'Ready to pick', tone: '#9FE1CB' },
      }
    },
  },
  methods: {
    setView(view) {
      this.$router.replace({ query: { ...this.$route.query, v: view } })
    },
    toast(body) {
      const id = (this.toastSeq += 1)
      this.toasts.push({ id, body })
      setTimeout(() => {
        this.toasts = this.toasts.filter((entry) => entry.id !== id)
      }, 4200)
    },
    sparkPath(values, width, height) {
      const max = Math.max(...values)
      const step = width / (values.length - 1)
      return values
        .map((value, index) => {
          const x = index * step
          const y = height - (value / max) * (height - 8) - 4
          return `${index ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`
        })
        .join(' ')
    },

    // --- agenda actions ---------------------------------------------------

    async act(item) {
      if (item.action === 'simulate-drive') return this.simulateDrive(item)
      if (item.action === 'nudge') {
        this.resolved = { ...this.resolved, [item.id]: 'Reminder sent · cited: blocked 4 days' }
        this.toast('Reminded Maya — with the citation, not just "ping".')
        return
      }
      if (item.action === 'amend') {
        this.resolved = { ...this.resolved, [item.id]: 'Rule 7 amended — lifestyle shots excluded' }
        this.rules = this.rules.map((rule) =>
          rule.id === 7
            ? { ...rule, amended: true, status: 'healthy', text: `${rule.text} (except lifestyle shots)` }
            : rule,
        )
        this.toast('Rule 7 amended. Precedent updated — future lifestyle shots pass.')
        return
      }
      if (item.action === 'show-rule') {
        this.highlightRule = 14
        this.setView('rules')
      }
    },
    keep(item) {
      this.resolved = { ...this.resolved, [item.id]: 'Kept as is — overrides will keep counting' }
    },
    dismiss(item) {
      this.resolved = { ...this.resolved, [item.id]: 'Dismissed' }
      this.toast(`Noted — I'll stop raising this. Dismissals teach the agenda too.`)
    },

    /** The Drive watched folder: ingestion has real latency, so fake it honestly. */
    async simulateDrive(item) {
      this.driveState = 'arriving'
      await WAIT(1600)
      this.driveState = 'reviewing'
      this.toast('hero_9x16.png arrived from Drive — run started, nobody clicked upload.')
      await WAIT(2600)
      this.driveState = 'done'
      this.slots = this.slots.map((slot) =>
        slot.id !== 'hero'
          ? slot
          : {
              ...slot,
              spec: slot.spec.map((entry) =>
                entry.format === '9x16' ? { ...entry, state: 'ready' } : entry,
              ),
            },
      )
      this.resolved = { ...this.resolved, [item.id]: '9:16 arrived via Drive · reviewed · clean' }
      this.agenda = [
        {
          id: 'pickable-916',
          kind: 'pickable',
          title: 'Hero 9:16 came back clean — it is pickable',
          cite: 'recheck passed 0 open · spec now only waits on your approval',
          action: 'show-slot',
          actionLabel: 'Open the slot',
        },
        ...this.agenda,
      ]
    },

    // --- the fix-as-branch loop ------------------------------------------

    async generateFix() {
      this.fixState = 'generating'
      for (const stage of GENERATION_STAGES) {
        this.fixStage = stage
        await WAIT(900)
      }
      this.tree = [
        ...this.tree,
        { id: 'c', parent: 'a', label: 'v2 alt', tone: '#5eead4', state: 'rechecking', who: 'QA agent' },
      ]
      this.selectedNode = 'c'
      this.fixState = 'rechecking'
      this.fixStage = 'Recheck running on the candidate…'
      await WAIT(2200)
      this.tree = this.tree.map((node) => (node.id === 'c' ? { ...node, state: 'clean' } : node))
      this.fixState = 'done'
      this.toast('Candidate passed recheck. It is a branch, not a decision — approving stays yours.')
    },

    approveShare() {
      this.shareBusy = true
      setTimeout(() => {
        this.shareBusy = false
        this.shareApproved = true
      }, 900)
    },

    stateChip(state) {
      return {
        approved: { label: 'Approved', dot: '#9FE1CB' },
        ready: { label: 'Ready to pick', dot: '#9FE1CB' },
        in_review: { label: 'In review', dot: '#a3a3a8' },
        blocked: { label: 'Blocked', dot: '#F09595' },
        missing: { label: 'Missing', dot: '#FAC775' },
        open: { label: '1 open', dot: '#FAC775' },
        clean: { label: 'Clean', dot: '#9FE1CB' },
        rechecking: { label: 'Rechecking…', dot: '#a3a3a8' },
      }[state]
    },
    reset() {
      Object.assign(this.$data, {
        slots: seedSlots(),
        agenda: seedAgenda(),
        rules: seedRules(),
        tree: seedTree(),
        resolved: {},
        driveState: 'idle',
        fixState: 'idle',
        fixStage: '',
        selectedNode: 'b',
        shareApproved: false,
        highlightRule: null,
      })
    },
  },
}
</script>

<template>
  <div class="min-h-[calc(100vh-49px)] pb-20">
    <!-- ═══ TODAY: the agenda loop, the app's front door ═══ -->
    <div v-if="view === 'today'" class="mx-auto max-w-2xl px-6 py-8">
      <header class="mb-6">
        <h2 class="text-lg font-medium text-neutral-50">Autumn Drop 04</h2>
        <p class="mt-0.5 text-xs text-neutral-500">
          Exports Fri 22 Aug ·
          <span class="text-neutral-300">{{ overduePressure }} things want a decision</span>
          · watching Drive /Autumn Drop
          <span
            v-if="driveState === 'arriving'"
            class="ml-1 animate-pulse text-teal-300"
          >file arriving…</span>
          <span
            v-else-if="driveState === 'reviewing'"
            class="ml-1 animate-pulse text-teal-300"
          >reviewing hero_9x16.png…</span>
        </p>
      </header>

      <p class="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">
        What I'd do next — every item cites its gap
      </p>

      <div class="space-y-2.5">
        <div
          v-for="item in agenda"
          :key="item.id"
          class="rounded-xl border p-3.5 transition"
          :class="resolved[item.id] ? 'border-edge opacity-50' : 'border-edge-strong bg-panel'"
        >
          <div class="flex items-start gap-3">
            <span
              class="mt-1 size-2 shrink-0 rounded-full"
              :style="{ background: kindMeta[item.kind].tone }"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-baseline gap-2">
                <span
                  class="text-[10px] uppercase tracking-wide"
                  :style="{ color: kindMeta[item.kind].tone }"
                >{{ kindMeta[item.kind].label }}</span>
              </div>
              <p class="mt-0.5 text-sm text-neutral-100">{{ item.title }}</p>
              <p class="mt-1 text-[11px] text-neutral-500">because: {{ item.cite }}</p>

              <div v-if="resolved[item.id]" class="mt-2 text-[11px] text-teal-200/80">
                ✓ {{ resolved[item.id] }}
              </div>
              <div v-else class="mt-2.5 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  class="rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900 hover:bg-white"
                  @click="item.action === 'show-slot' ? setView('slot') : act(item)"
                >
                  {{ item.actionLabel }}
                </button>
                <button
                  v-if="item.secondary"
                  type="button"
                  class="rounded-md border border-neutral-600 px-2.5 py-1 text-[11px] text-neutral-300 hover:bg-edge"
                  @click="keep(item)"
                >
                  {{ item.secondary }}
                </button>
                <button
                  type="button"
                  class="ml-auto text-[11px] text-neutral-600 hover:text-neutral-300"
                  @click="dismiss(item)"
                >
                  not useful
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- the spec board: definition of done, per slot -->
      <p class="mb-2 mt-8 text-[10px] uppercase tracking-widest text-neutral-500">
        Slots against their spec
      </p>
      <div class="space-y-2">
        <button
          v-for="slot in slots"
          :key="slot.id"
          type="button"
          class="flex w-full items-center gap-3 rounded-xl border border-edge bg-panel px-3.5 py-3 text-left hover:border-edge-strong"
          @click="setView('slot')"
        >
          <span class="min-w-0 flex-1 truncate text-sm text-neutral-200">{{ slot.name }}</span>
          <span class="flex gap-1.5">
            <span
              v-for="entry in slot.spec"
              :key="entry.format"
              class="flex items-center gap-1 rounded-full border border-edge-strong px-2 py-0.5 text-[10px] text-neutral-300"
            >
              <span class="size-1.5 rounded-full" :style="{ background: stateChip(entry.state).dot }" />
              {{ entry.format }}
            </span>
          </span>
          <span class="text-[10px] text-neutral-600">{{ slot.due }}</span>
        </button>
      </div>
    </div>

    <!-- ═══ SLOT: verdict never arrives alone ═══ -->
    <div v-else-if="view === 'slot'" class="mx-auto max-w-3xl px-6 py-8">
      <header class="mb-5">
        <h2 class="text-lg font-medium text-neutral-50">Hero banner · 1x1</h2>
        <p class="mt-0.5 text-xs text-neutral-500">
          Spec: 16x9 approved · 1x1 in play (below) · 9:16
          {{ driveState === 'done' ? 'ready to pick' : 'missing' }}
        </p>
      </header>

      <div class="grid gap-5 md:grid-cols-[1fr_300px]">
        <!-- lineage strip: enough tree to anchor the branch moment -->
        <div class="rounded-xl border border-edge bg-panel p-4">
          <p class="mb-3 text-[10px] uppercase tracking-widest text-neutral-500">Lineage</p>
          <div class="flex items-start gap-6">
            <div
              v-for="entry in tree"
              :key="entry.id"
              class="relative"
            >
              <button
                type="button"
                class="w-32 rounded-lg border p-2 text-left transition"
                :class="[
                  selectedNode === entry.id ? 'ring-2 ring-neutral-300' : '',
                  entry.state === 'clean' && entry.who === 'QA agent'
                    ? 'border-teal-400/60 bg-teal-400/10'
                    : 'border-edge-strong bg-panel-2 hover:border-neutral-500',
                ]"
                @click="selectedNode = entry.id"
              >
                <div class="h-14 rounded" :style="{ background: entry.tone }" />
                <div class="mt-1.5 flex items-center justify-between">
                  <span class="font-mono text-[11px] text-neutral-100">{{ entry.label }}</span>
                  <span class="text-[9px] text-neutral-500">{{ entry.who }}</span>
                </div>
                <div class="mt-0.5 flex items-center gap-1 text-[10px] text-neutral-400">
                  <span
                    class="size-1.5 rounded-full"
                    :class="entry.state === 'rechecking' ? 'animate-pulse' : ''"
                    :style="{ background: stateChip(entry.state).dot }"
                  />
                  {{ stateChip(entry.state).label }}
                </div>
              </button>
              <div
                v-if="entry.parent"
                class="absolute -left-6 top-1/2 h-px w-6 bg-neutral-600"
              />
            </div>
          </div>
          <p class="mt-3 text-[10px] text-neutral-600">
            supersedes flows left → right · a second fix of the same parent is a branch
          </p>
        </div>

        <!-- the verdict card -->
        <div class="rounded-xl border border-edge bg-panel p-4">
          <p class="mb-2 text-[10px] uppercase tracking-widest text-neutral-500">
            Verdict on {{ node?.label }}
          </p>

          <template v-if="selectedNode === 'a'">
            <div class="rounded-lg border border-warning/40 bg-warning/5 p-2.5">
              <p class="text-xs text-neutral-100">Logo sits on busy photographic ground</p>
              <p class="mt-1 text-[10px] text-neutral-500">
                cites <button class="underline decoration-dotted" @click="highlightRule = 14; setView('rules')">rule 14</button>
                · measured: local contrast 1.8:1, brand floor 3:1
              </p>
              <div class="mt-2 rounded bg-panel-2 p-2 text-[11px] text-neutral-300">
                <span class="text-teal-300">Proposed remedy:</span> move the logo to the
                top-left quiet area; ground there measures 6.2:1.
              </div>
              <div class="mt-2 flex gap-1.5">
                <button
                  type="button"
                  class="flex-1 rounded-md bg-neutral-50 px-2 py-1 text-[11px] font-medium text-neutral-900 disabled:opacity-40"
                  :disabled="fixState !== 'idle'"
                  @click="generateFix"
                >
                  Generate the fix
                </button>
                <button
                  type="button"
                  class="flex-1 rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-300 hover:bg-edge"
                >
                  Send to Maya instead
                </button>
              </div>
              <p class="mt-1.5 text-[9px] text-neutral-600">
                mechanical fixes the agent may generate · creative calls go to the designer first
              </p>
            </div>
          </template>

          <template v-else>
            <p class="text-xs text-neutral-300">
              {{ node?.state === 'clean' ? 'Nothing outstanding on this version.' : 'Recheck in progress…' }}
            </p>
            <button
              v-if="node?.state === 'clean'"
              type="button"
              class="mt-3 w-full rounded-md border border-teal-400/60 px-2 py-1.5 text-[11px] text-teal-200 hover:bg-teal-400/10"
            >
              Approve this version
            </button>
            <p class="mt-1.5 text-center text-[9px] text-neutral-600">
              approval never leaves the human
            </p>
          </template>

          <div
            v-if="fixState === 'generating' || fixState === 'rechecking'"
            class="mt-3 flex items-center gap-2 rounded-lg border border-edge-strong bg-panel-2 px-2.5 py-2"
          >
            <span class="size-1.5 animate-pulse rounded-full bg-teal-300" />
            <span class="text-[11px] text-neutral-300">{{ fixStage }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ RULEBOOK: case law with a pulse ═══ -->
    <div v-else-if="view === 'rules'" class="mx-auto max-w-2xl px-6 py-8">
      <header class="mb-5">
        <h2 class="text-lg font-medium text-neutral-50">Rulebook</h2>
        <p class="mt-0.5 text-xs text-neutral-500">
          What this brand has taught the agent — statute, case law, precedent
        </p>
      </header>

      <div class="mb-6 rounded-xl border border-edge bg-panel p-4">
        <div class="flex items-baseline justify-between">
          <p class="text-[10px] uppercase tracking-widest text-neutral-500">
            Override rate · the one health metric
          </p>
          <p class="text-[11px] text-teal-300">34% → 7% over 6 weeks</p>
        </div>
        <svg viewBox="0 0 320 72" class="mt-2 h-16 w-full">
          <path :d="healthLine" fill="none" stroke="#5eead4" stroke-width="2" stroke-linecap="round" />
        </svg>
        <p class="text-[10px] text-neutral-600">
          every point is you correcting the agent less — that curve is the product learning your taste
        </p>
      </div>

      <div class="space-y-2.5">
        <div
          v-for="rule in rules"
          :key="rule.id"
          class="rounded-xl border p-3.5 transition"
          :class="highlightRule === rule.id ? 'border-teal-400/60 bg-teal-400/5' : 'border-edge-strong bg-panel'"
        >
          <div class="flex items-baseline gap-2">
            <span class="font-mono text-[11px] text-neutral-500">rule {{ rule.id }}</span>
            <span class="min-w-0 flex-1 text-sm text-neutral-100">{{ rule.text }}</span>
            <span
              v-if="rule.status === 'dying'"
              class="rounded-full border border-blocker/40 px-2 py-0.5 text-[9px] text-blocker"
            >dying precedent</span>
            <span
              v-else-if="rule.status === 'contested'"
              class="rounded-full border border-warning/40 px-2 py-0.5 text-[9px] text-warning"
            >contested</span>
            <span
              v-else-if="rule.amended"
              class="rounded-full border border-teal-400/40 px-2 py-0.5 text-[9px] text-teal-300"
            >amended today</span>
          </div>
          <div class="mt-1.5 flex items-center gap-3 text-[10px] text-neutral-500">
            <span>{{ rule.born }}</span>
            <span>cited {{ rule.cited }}×</span>
            <span :class="rule.overridden > rule.cited / 3 ? 'text-warning' : ''">
              overridden {{ rule.overridden }}×
            </span>
            <svg viewBox="0 0 60 16" class="ml-auto h-4 w-16">
              <path
                :d="sparkPath(rule.trend, 60, 16)"
                fill="none"
                :stroke="rule.status === 'dying' ? '#F09595' : '#8b8b96'"
                stroke-width="1.5"
              />
            </svg>
          </div>
          <div v-if="rule.status === 'dying'" class="mt-2 flex items-center gap-2">
            <p class="text-[11px] text-neutral-400">
              Overridden 5 of its last 6 citations — retire it?
            </p>
            <button
              type="button"
              class="rounded-md border border-neutral-600 px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-edge"
              @click="rules = rules.filter((r) => r.id !== rule.id); toast('Rule 9 retired. The rulebook gardens itself.')"
            >
              Retire
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ SHARE LINK: the client's whole world is one decision ═══ -->
    <div v-else class="flex min-h-[70vh] items-center justify-center px-6">
      <div class="w-full max-w-md">
        <p class="mb-3 text-center text-[10px] uppercase tracking-widest text-neutral-600">
          what the client sees — no account, no app, one link
        </p>
        <div class="rounded-2xl border border-edge-strong bg-panel p-5 shadow-2xl shadow-black/50">
          <div class="h-52 rounded-lg" style="background: #3b5a8a" />
          <div class="mt-3">
            <p class="text-sm font-medium text-neutral-100">Hero banner · 1x1 · v2</p>
            <p class="mt-0.5 text-[11px] text-neutral-500">
              Autumn Drop 04 · from Marikreasi Digital
            </p>
          </div>
          <div class="mt-3 rounded-lg bg-panel-2 p-2.5 text-[11px] leading-relaxed text-neutral-300">
            <span class="text-teal-300">QA agent:</span> 0 blockers · passed brand palette,
            contrast and platform safe-area checks · 2 advisory notes on file
          </div>
          <template v-if="!shareApproved">
            <button
              type="button"
              class="mt-3 w-full rounded-lg bg-neutral-50 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:opacity-50"
              :disabled="shareBusy"
              @click="approveShare"
            >
              {{ shareBusy ? 'Recording…' : 'Approve for release' }}
            </button>
            <p class="mt-2 text-center text-[10px] text-neutral-600">
              or reply with a note — either way it lands in the tree
            </p>
          </template>
          <div v-else class="mt-3 rounded-lg border border-teal-400/40 bg-teal-400/5 p-3 text-center">
            <p class="text-sm text-teal-200">Approved ✓</p>
            <p class="mt-1 text-[10px] text-neutral-500">
              recorded: client@brand.com · 16 Aug 14:02 · over 2 explored alternatives ·
              this line is the audit answer
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- toasts: the partner narrating what it just did -->
    <div class="pointer-events-none fixed bottom-16 left-1/2 z-40 w-full max-w-md -translate-x-1/2 space-y-2 px-4">
      <div
        v-for="entry in toasts"
        :key="entry.id"
        class="rounded-lg border border-edge-strong bg-panel-2/95 px-3 py-2 text-[11px] text-neutral-200 shadow-xl backdrop-blur"
      >
        {{ entry.body }}
      </div>
    </div>

    <!-- switcher -->
    <div class="fixed bottom-0 left-0 right-0 z-30 border-t border-edge-strong bg-ink/90 px-6 py-2.5 backdrop-blur">
      <div class="flex flex-wrap items-center justify-center gap-3">
        <span class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">
          prototype
        </span>
        <div class="flex gap-1">
          <button
            v-for="option in [
              { id: 'today', label: 'Today' },
              { id: 'slot', label: 'Slot' },
              { id: 'rules', label: 'Rulebook' },
              { id: 'share', label: 'Share link' },
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
