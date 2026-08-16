<script>
/**
 * PROTOTYPE — throwaway. Not wired to the API, not tested.
 *
 * Question: where do the partner behaviors sit in the UI we already shipped?
 * This mocks the real ProjectPage and SlotFlowPage layouts and inserts the new
 * pieces in their actual homes:
 *
 *   - debrief panel  → where ProjectPage's "agent working" strip lives
 *   - judgment lines → the activity feed's voice, upgraded
 *   - drafted fixes  → branches on the real tree canvas, marked as agent's
 *   - the stance     → the SlotFlowPage rail, above the approve button
 *   - intake question→ the upload staging strip
 *
 * "Next morning" jumps time — initiative is only visible in your absence.
 * Toggle "highlight new" to see exactly what is being added to the shipped UI.
 */

const WAIT = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function daySlots(morning) {
  return [
    {
      id: 'hero',
      name: 'Hero banner',
      tone: '#8a5a3b',
      variants: 2,
      pill: morning
        ? { label: 'Ready — pick 1 of 2', dot: '#9FE1CB' }
        : { label: '2 open', dot: '#FAC775' },
    },
    {
      id: 'pdp',
      name: 'Product detail set',
      tone: '#3b5a8a',
      variants: 1,
      pill: morning ? { label: 'Reviewing…', dot: '#a3a3a8', pulse: true } : { label: 'Clean', dot: '#9FE1CB' },
    },
    {
      id: 'story',
      name: 'Story teaser',
      tone: '#3b7a5a',
      variants: 1,
      pill: morning ? { label: 'Clean', dot: '#9FE1CB' } : { label: '1 open', dot: '#FAC775' },
    },
  ]
}

function morningTree() {
  // `look` drives the mock render: the defects are VISIBLE, so every claim the
  // agent makes about a version can be checked against the thumbnail itself.
  return [
    { id: 'a', parent: null, col: 0, row: 0, v: 'v1', who: 'Maya', look: 'broken', state: '2 open', dot: '#FAC775' },
    { id: 'b', parent: 'a', col: 0, row: 1, v: 'v2', who: 'QA agent', look: 'fixed', state: 'Clean', dot: '#9FE1CB', draft: true },
    { id: 'c', parent: null, col: 1, row: 0, v: 'v1', who: 'Leo', look: 'cropped', state: 'Clean', dot: '#9FE1CB' },
  ]
}

export default {
  name: 'PrototypePartnerPage',
  data() {
    return {
      view: 'project', // project | slot
      tab: 'assets', // assets | activity
      morning: false, // has time passed yet
      overnight: '', // fake-latency line while the night "runs"
      showNew: true,
      staged: false, // upload staging strip open
      placement: '',
      tree: [],
      selected: null,
      picked: false,
      tealAnswered: '',
      tealOpen: false,
      stripDismissed: false,
      reviewVersion: 'fixed',
      activePin: null,
      toasts: [],
      toastSeq: 0,
    }
  },
  computed: {
    slots() {
      return daySlots(this.morning)
    },
    byId() {
      return Object.fromEntries(this.tree.map((node) => [node.id, node]))
    },
    judgmentFeed() {
      return [
        'kept quiet about a drop shadow on pdp_03 — rule #1 says shadows are fine',
        'drafted a fix for the hero contrast instead of just flagging it — it is reversible, so I acted first',
        'did NOT draft a fix for the crop complaint — that is a creative call, Maya should make it',
        'reminded Maya about the stalled 4x5 — day 2, next step would be escalating to you',
      ]
    },
  },
  methods: {
    toast(body) {
      const id = (this.toastSeq += 1)
      this.toasts.push({ id, body })
      setTimeout(() => {
        this.toasts = this.toasts.filter((entry) => entry.id !== id)
      }, 4600)
    },

    /** Time passes. Initiative needs an absence to be visible in. */
    async nextMorning() {
      this.overnight = 'Night passes — 3 files arrive in the Drive folder…'
      await WAIT(1500)
      this.overnight = 'Reviewing them · drafting fixes for the mechanical defects…'
      await WAIT(1800)
      this.overnight = ''
      this.morning = true
      this.tree = morningTree()
      this.selected = 'b'
    },

    answerTeal(inBrand) {
      this.tealAnswered = inBrand
        ? 'in brand — noted, tolerance widened'
        : 'flagged — CTA colours get the strict treatment'
    },

    makePick() {
      this.picked = true
      this.toast('Recorded: approved by you, on my recommendation. Your reasons, not mine, go in the audit line.')
    },
    discardDraft() {
      this.tree = this.tree.filter((node) => !node.draft)
      this.selected = 'c'
      this.toast('Draft discarded — it was only ever a branch. I will propose instead of draft for this slot from now on.')
    },

    choosePlacement(where) {
      this.placement = where
      this.toast(
        where === 'TikTok'
          ? 'Noted — I will watch the bottom-UI safe area on every 9:16 in this batch.'
          : `Noted — checking ${where} placement rules for this batch.`,
      )
    },

    edge(node) {
      const parent = this.byId[node.parent]
      if (!parent) return ''
      const x1 = parent.col * 210 + 84
      const y1 = parent.row * 150 + 100
      const x2 = node.col * 210 + 84
      const y2 = node.row * 150 + 4
      if (Math.abs(x1 - x2) < 1) return `M ${x1} ${y1} L ${x2} ${y2}`
      const bus = y2 - 22
      return `M ${x1} ${y1} L ${x1} ${bus} L ${x2} ${bus} L ${x2} ${y2}`
    },
    newClass(active = true) {
      return this.showNew && active ? 'outline outline-2 outline-offset-2 outline-warning/60' : ''
    },
    reset() {
      Object.assign(this.$data, {
        view: 'project',
        tab: 'assets',
        morning: false,
        overnight: '',
        staged: false,
        placement: '',
        tree: [],
        selected: null,
        picked: false,
        tealAnswered: '',
        tealOpen: false,
        stripDismissed: false,
        reviewVersion: 'fixed',
        activePin: null,
      })
    },
  },
}
</script>

<template>
  <div class="min-h-[calc(100vh-49px)] pb-20">
    <!-- ═══════════════ PROJECT PAGE (mock of the shipped one) ═══════════════ -->
    <div v-if="view === 'project'" class="mx-auto max-w-6xl px-6 py-6">
      <span class="text-xs text-neutral-500">← All projects</span>
      <header class="mt-1 flex flex-wrap items-center gap-3">
        <h2 class="text-xl font-medium tracking-tight">Autumn Drop 04</h2>
        <span class="rounded-full border border-edge-strong px-2 py-0.5 text-[11px] text-neutral-400">owner</span>
        <button
          type="button"
          class="ml-auto rounded-md bg-neutral-50 px-3 py-1.5 text-sm font-medium text-neutral-900 hover:bg-white"
          @click="staged = true"
        >
          Add images
        </button>
      </header>

      <nav class="mt-4 flex gap-5 border-b border-edge text-sm">
        <button
          type="button"
          class="-mb-px border-b-2 pb-2.5"
          :class="tab === 'assets' ? 'border-neutral-100 font-medium text-neutral-100' : 'border-transparent text-neutral-500'"
          @click="tab = 'assets'"
        >
          Slots 3
        </button>
        <button
          type="button"
          class="-mb-px border-b-2 pb-2.5"
          :class="tab === 'activity' ? 'border-neutral-100 font-medium text-neutral-100' : 'border-transparent text-neutral-500'"
          @click="tab = 'activity'"
        >
          Activity
        </button>
        <span class="pb-2.5 text-neutral-500">Settings</span>
      </nav>

      <!-- NEW · the activity feed speaks in judgments, not pipeline stages -->
      <div v-if="tab === 'activity'" class="mt-5 max-w-2xl space-y-2" :class="newClass()">
        <div
          v-for="line in judgmentFeed"
          :key="line"
          class="rounded-md border border-edge px-3 py-2 text-xs text-neutral-300"
        >
          {{ line }}
        </div>
        <p class="pt-1 text-[11px] text-neutral-600">
          this is the shipped activity feed — the voice changed from "inspecting cell D4"
          to why it acted
        </p>
      </div>

      <!-- NEW · intake question — lives in the upload staging strip -->
      <div
        v-if="staged"
        class="mt-5 rounded-lg border border-edge-strong bg-panel p-3"
        :class="newClass()"
      >
        <div class="flex items-center gap-2">
          <span v-for="n in 3" :key="n" class="h-10 w-10 rounded bg-edge" />
          <span class="text-xs text-neutral-400">3 files staged</span>
          <button type="button" class="ml-auto text-xs text-neutral-500" @click="staged = false">✕</button>
        </div>
        <div class="mt-2.5 border-t border-edge pt-2.5">
          <p class="text-xs text-neutral-200">
            <span class="text-teal-300">One question before I look:</span> where will these run?
            It changes what I watch for.
          </p>
          <div class="mt-2 flex gap-1.5">
            <button
              v-for="where in ['TikTok', 'Instagram', 'Web']"
              :key="where"
              type="button"
              class="rounded-md px-2.5 py-1 text-[11px]"
              :class="placement === where ? 'bg-neutral-50 font-medium text-neutral-900' : 'border border-neutral-600 text-neutral-300 hover:bg-edge'"
              @click="choosePlacement(where)"
            >
              {{ where }}
            </button>
            <span class="self-center text-[10px] text-neutral-600">TikTok → bottom-UI safe area on every 9:16</span>
          </div>
        </div>
      </div>

      <!-- the shipped "agent working" strip — before morning, unchanged behavior -->
      <div
        v-if="!morning && !overnight && tab === 'assets'"
        class="mt-5 flex items-center gap-2.5 rounded-md border border-edge px-3 py-2"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-teal-300" />
        <span class="text-xs text-neutral-400">Agent working on 2 slots · inspecting suspect cells</span>
        <span class="ml-auto text-xs text-neutral-500">Watch</span>
      </div>

      <!-- overnight passing -->
      <div v-if="overnight" class="mt-5 flex items-center gap-2.5 rounded-md border border-edge px-3 py-2">
        <span class="size-1.5 animate-pulse rounded-full bg-teal-300" />
        <span class="text-xs text-neutral-300">{{ overnight }}</span>
      </div>

      <!-- ═══ NEW · one quiet line, not a memo — everything else lives in the cards ═══ -->
      <div
        v-if="morning && tab === 'assets' && !stripDismissed"
        class="mt-5 flex items-center gap-2.5 rounded-md border border-edge px-3 py-2"
        :class="newClass()"
      >
        <span class="text-xs text-neutral-500">☾</span>
        <span class="text-xs text-neutral-400">
          Overnight: reviewed 3 new files ·
          <button class="text-teal-300 hover:underline" @click="view = 'slot'">drafted a fix for Hero</button>
          · nudged Maya ·
          <button class="text-neutral-300 hover:underline" @click="tealOpen = true">one question</button>
        </span>
        <button
          type="button"
          class="ml-auto text-xs text-neutral-600 hover:text-neutral-300"
          @click="stripDismissed = true"
        >
          ✕
        </button>
      </div>

      <!-- the shipped slot grid — the agent's work shows up ON the cards, in place -->
      <div v-if="tab === 'assets'" class="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="slot in slots"
          :key="slot.id"
          class="group relative overflow-hidden rounded-lg border border-edge bg-panel transition hover:border-edge-strong"
          :class="slot.id === 'hero' && morning ? 'cursor-pointer' : ''"
          @click="slot.id === 'hero' && morning ? (view = 'slot') : null"
        >
          <div class="aspect-square w-full" :style="{ background: slot.tone }" />
          <div class="flex items-center gap-2 px-3 py-2.5">
            <span class="min-w-0 truncate text-sm text-neutral-200">{{ slot.name }}</span>
            <span
              v-if="slot.variants > 1"
              class="shrink-0 rounded-full border border-edge-strong px-1.5 text-[10px] text-neutral-500"
            >{{ slot.variants }} variants</span>
            <span class="ml-auto flex shrink-0 items-center gap-1.5 text-[11px] text-neutral-400">
              <span
                class="size-1.5 rounded-full"
                :class="slot.pill.pulse ? 'animate-pulse' : ''"
                :style="{ background: slot.pill.dot }"
              />
              {{ slot.pill.label }}
            </span>
          </div>

          <!-- NEW · marks of the agent's overnight work, discovered in place -->
          <div
            v-if="morning && slot.id === 'hero' && !picked"
            class="border-t border-edge px-3 py-1.5"
            :class="newClass()"
          >
            <span class="rounded-full border border-dashed border-teal-400/50 px-1.5 py-0.5 text-[10px] text-teal-300">
              draft ready — my pick is in
            </span>
          </div>
          <div
            v-if="morning && slot.id === 'story' && !tealAnswered"
            class="border-t border-edge px-3 py-1.5"
            :class="newClass()"
          >
            <button
              type="button"
              class="rounded-full border border-neutral-600 px-1.5 py-0.5 text-[10px] text-neutral-300 hover:bg-edge"
              @click.stop="tealOpen = !tealOpen"
            >
              1 question for you
            </button>
            <!-- asked in place, answerable in place, ignorable forever -->
            <div v-if="tealOpen" class="mt-2 rounded-md bg-panel-2 p-2.5" @click.stop>
              <p class="text-[11px] leading-relaxed text-neutral-200">
                Is this teal in brand? Judge for yourself:
              </p>
              <div class="mt-1.5 flex items-center gap-2">
                <span class="flex flex-col items-center gap-0.5">
                  <span class="h-7 w-12 rounded ring-1 ring-inset ring-white/15" style="background: #2fa584" />
                  <span class="text-[9px] text-neutral-500">your brand teal</span>
                </span>
                <span class="flex flex-col items-center gap-0.5">
                  <span class="h-7 w-12 rounded ring-1 ring-inset ring-white/15" style="background: #2aa47d" />
                  <span class="text-[9px] text-neutral-500">this CTA</span>
                </span>
                <span class="self-start pt-1.5 text-[10px] text-neutral-400">
                  ΔE 2.2 — near twins. But it's on a CTA, and I've been wrong about teal twice.
                </span>
              </div>
              <div class="mt-1.5 flex gap-1.5">
                <button
                  type="button"
                  class="rounded bg-neutral-50 px-2 py-0.5 text-[10px] font-medium text-neutral-900"
                  @click="answerTeal(true); tealOpen = false"
                >
                  In brand
                </button>
                <button
                  type="button"
                  class="rounded border border-neutral-600 px-2 py-0.5 text-[10px] text-neutral-300"
                  @click="answerTeal(false); tealOpen = false"
                >
                  Flag it
                </button>
                <button
                  type="button"
                  class="ml-auto text-[10px] text-neutral-600"
                  @click="tealOpen = false"
                >
                  later
                </button>
              </div>
            </div>
          </div>
          <div
            v-if="morning && slot.id === 'story' && tealAnswered"
            class="border-t border-edge px-3 py-1.5 text-[10px] text-teal-200/80"
          >
            ✓ {{ tealAnswered }}
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ REVIEW PAGE (mock of the shipped one) ═══════════════ -->
    <div v-else-if="view === 'review'" class="mx-auto max-w-6xl px-6 py-5">
      <div class="flex items-center gap-3">
        <button type="button" class="text-xs text-neutral-500 hover:text-neutral-200" @click="view = 'slot'">
          ← Tree
        </button>
        <span class="text-sm text-neutral-100">hero_draft.png</span>
        <span class="text-[11px] text-neutral-500">Variant 1 · v2 of 2</span>

        <!-- the shipped version strip — flipping IS the verification -->
        <div class="ml-6 flex gap-1" :class="newClass()">
          <button
            v-for="option in [
              { id: 'broken', label: 'V1' },
              { id: 'fixed', label: '★ V2 draft' },
            ]"
            :key="option.id"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs"
            :class="
              reviewVersion === option.id
                ? 'bg-neutral-50 font-medium text-neutral-900'
                : 'border border-neutral-600 text-neutral-300 hover:bg-edge'
            "
            @click="reviewVersion = option.id"
          >
            {{ option.label }}
          </button>
          <span class="self-center pl-1 text-[10px] text-neutral-500">flip between them — see the claims yourself</span>
        </div>
      </div>

      <div class="mt-4 grid gap-5 lg:grid-cols-[1fr_320px]">
        <!-- the canvas: full-size, pins where the defects are -->
        <div class="relative mx-auto w-full max-w-2xl">
          <div class="relative aspect-[4/3] overflow-hidden rounded-lg bg-[#8a5a3b] ring-1 ring-inset ring-white/10">
            <span
              class="absolute bottom-[12%] left-[8%] flex h-[10%] w-[58%] items-center rounded pl-3 text-sm font-medium transition-colors duration-300"
              :style="{ color: reviewVersion === 'fixed' ? '#f5ede2' : '#a3805e' }"
            >
              AUTUMN — UP TO 40% OFF
            </span>
            <span
              class="absolute right-[8%] top-[8%] flex h-[16%] w-[16%] items-center justify-center rounded bg-white/85 text-[10px] font-semibold text-neutral-800 transition-transform duration-300"
              :class="reviewVersion === 'broken' ? 'rotate-12' : ''"
            >
              LOGO
            </span>

            <!-- pins, exactly like the shipped review canvas -->
            <button
              type="button"
              class="absolute bottom-[20%] left-[30%] flex size-6 items-center justify-center rounded-full text-[11px] font-semibold text-neutral-900 ring-2 ring-black/40"
              :style="{ background: reviewVersion === 'fixed' ? '#9FE1CB' : '#FAC775' }"
              @click="activePin = activePin === 1 ? null : 1"
            >
              1
            </button>
            <button
              type="button"
              class="absolute right-[6%] top-[26%] flex size-6 items-center justify-center rounded-full text-[11px] font-semibold text-neutral-900 ring-2 ring-black/40"
              :style="{ background: reviewVersion === 'fixed' ? '#9FE1CB' : '#FAC775' }"
              @click="activePin = activePin === 2 ? null : 2"
            >
              2
            </button>
          </div>
          <p class="mt-2 text-center text-[11px] text-neutral-500">
            {{ reviewVersion === 'fixed' ? 'the draft — headline readable, logo square' : 'Maya\'s v1 — try reading the headline' }}
          </p>
        </div>

        <!-- defect threads, measurement stamped, resolution stated -->
        <div class="space-y-2.5">
          <div
            class="rounded-lg border p-3 transition"
            :class="activePin === 1 ? 'border-neutral-400 bg-panel' : 'border-edge-strong bg-panel'"
          >
            <p class="text-xs text-neutral-100">1 · Headline contrast below brand floor</p>
            <p class="mt-1 text-[11px] leading-relaxed text-neutral-400">
              Measured 2.1:1 on v1 against a floor of 3:1 (rule #2, from your brand PDF).
              The draft moves it to <span class="text-neutral-200">4.8:1</span> — flip the
              version strip and read the headline both ways.
            </p>
            <p class="mt-1.5 text-[10px]" :class="reviewVersion === 'fixed' ? 'text-teal-300' : 'text-warning'">
              {{ reviewVersion === 'fixed' ? '✓ resolved in the draft you are looking at' : '● open on this version' }}
            </p>
          </div>
          <div
            class="rounded-lg border p-3 transition"
            :class="activePin === 2 ? 'border-neutral-400 bg-panel' : 'border-edge-strong bg-panel'"
          >
            <p class="text-xs text-neutral-100">2 · Logo warped</p>
            <p class="mt-1 text-[11px] leading-relaxed text-neutral-400">
              Top-right corner, skewed ~12°. The draft redraws it square — flip and watch the corner.
            </p>
            <p class="mt-1.5 text-[10px]" :class="reviewVersion === 'fixed' ? 'text-teal-300' : 'text-warning'">
              {{ reviewVersion === 'fixed' ? '✓ resolved in the draft you are looking at' : '● open on this version' }}
            </p>
          </div>

          <!-- NEW · the stance travels with you, actions where the evidence is -->
          <div class="rounded-lg border border-teal-400/40 bg-teal-400/5 p-3" :class="newClass()">
            <p class="text-[10px] uppercase tracking-wide text-teal-300">My call</p>
            <p class="mt-1 text-[11px] leading-relaxed text-neutral-300">
              Ship this draft. Both defects resolve, nothing new appeared, and the alternative
              clips the product.
            </p>
            <div class="mt-2 flex gap-1.5">
              <button
                type="button"
                class="flex-1 rounded-md bg-neutral-50 px-2 py-1 text-[11px] font-medium text-neutral-900"
                @click="makePick(); view = 'slot'"
              >
                Approve this version
              </button>
              <button
                type="button"
                class="flex-1 rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-300"
                @click="discardDraft(); view = 'slot'"
              >
                Discard draft
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ SLOT FLOW (mock of the shipped canvas) ═══════════════ -->
    <div v-else class="relative">
      <div
        class="pointer-events-none fixed inset-0"
        style="
          background-image:
            linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
          background-size: 40px 40px;
        "
      />
      <header class="relative z-20 flex h-12 items-center gap-3 border-b border-edge-strong bg-ink/90 px-4 backdrop-blur xl:pr-[356px]">
        <button type="button" class="text-xs text-neutral-500 hover:text-neutral-200" @click="view = 'project'">
          ← Slots
        </button>
        <span class="text-sm font-medium text-neutral-100">Hero banner</span>
        <span class="text-[11px] text-neutral-400">2 variants · 3 versions</span>
      </header>

      <div class="relative xl:pr-[340px]">
        <div class="relative mx-auto mt-10 h-[420px] w-[400px]">
          <svg class="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
            <path
              v-for="node in tree.filter((n) => n.parent)"
              :key="`e-${node.id}`"
              :d="edge(node)"
              fill="none"
              stroke-linecap="round"
              :stroke="node.draft ? '#5eead4' : '#8b8b96'"
              :stroke-width="2"
              :stroke-dasharray="node.draft ? '5 4' : ''"
            />
          </svg>

          <button
            v-for="node in tree"
            :key="node.id"
            type="button"
            class="absolute w-[168px] rounded-xl border p-2.5 text-left shadow-xl shadow-black/50 transition"
            :style="{ left: `${node.col * 210}px`, top: `${node.row * 150 + 4}px` }"
            :class="[
              picked && node.draft
                ? 'border-teal-400/70 bg-teal-400/10'
                : node.draft
                  ? 'border-dashed border-teal-400/60 bg-panel-2'
                  : 'border-edge-strong bg-panel-2 hover:border-neutral-500',
              selected === node.id ? 'ring-2 ring-neutral-300' : '',
              node.draft ? newClass() : '',
            ]"
            @click="selected = node.id"
          >
            <div class="flex items-center gap-2.5">
              <!-- the defect is drawn, not described: dim headline, warped logo, clipped product -->
              <div class="relative h-9 w-12 shrink-0 overflow-hidden rounded bg-[#8a5a3b] ring-1 ring-inset ring-white/10">
                <template v-if="node.look !== 'cropped'">
                  <span
                    class="absolute bottom-[12%] left-[8%] h-[16%] w-[58%] rounded-[1px]"
                    :style="{ background: node.look === 'fixed' ? '#f5ede2' : '#a3805e' }"
                  />
                  <span
                    class="absolute right-[8%] top-[10%] h-[24%] w-[24%] rounded-[1px] bg-white/80"
                    :class="node.look === 'broken' ? 'rotate-12' : ''"
                  />
                </template>
                <span
                  v-else
                  class="absolute right-[-20%] top-1/2 aspect-square w-[58%] -translate-y-1/2 rounded-full bg-[#e8d9c5]"
                />
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="font-mono text-xs text-neutral-100">{{ node.v }}</span>
                  <span
                    v-if="node.draft"
                    class="rounded-full border border-teal-400/50 px-1.5 text-[9px] text-teal-300"
                  >{{ picked ? 'approved' : 'draft · by agent' }}</span>
                </div>
                <div class="truncate text-[11px] text-neutral-400">{{ node.who }}</div>
              </div>
            </div>
            <div class="mt-2 flex items-center gap-1.5 text-[10px] text-neutral-300">
              <span class="size-1.5 rounded-full" :style="{ background: node.dot }" />
              {{ picked && node.draft ? 'Approved' : node.state }}
            </div>
          </button>
        </div>
      </div>

      <!-- the shipped rail, with the stance panel added above the actions -->
      <aside class="fixed bottom-0 right-0 top-[49px] z-20 hidden w-[340px] flex-col border-l border-edge-strong bg-panel/95 backdrop-blur xl:flex">
        <header class="border-b border-edge-strong px-4 py-3">
          <div class="text-[10px] uppercase tracking-widest text-neutral-400">Selected version</div>
          <div v-if="byId[selected]" class="mt-0.5 text-xs text-neutral-100">
            {{ byId[selected].v }} · {{ byId[selected].who }} · {{ byId[selected].state }}
          </div>
        </header>

        <div class="flex-1 overflow-y-auto px-4 py-3">
          <!-- ═══ NEW · THE STANCE — the agent's pick, above your buttons ═══ -->
          <div
            v-if="!picked && tree.some((n) => n.draft)"
            class="rounded-lg border border-teal-400/40 bg-teal-400/5 p-3"
            :class="newClass()"
          >
            <p class="text-[10px] uppercase tracking-wide text-teal-300">My call</p>
            <p class="mt-1 text-xs leading-relaxed text-neutral-200">
              I'd ship <span class="font-mono">v2</span> — the draft. It clears both defects;
              the other clean option puts the product on the frame edge.
            </p>
            <p class="mt-1 text-[10px] text-neutral-500">
              a recommendation, not a decision — verify it where verifying lives:
            </p>
            <button
              type="button"
              class="mt-2.5 w-full rounded-md bg-neutral-50 px-2 py-1.5 text-[11px] font-medium text-neutral-900 hover:bg-white"
              @click="view = 'review'"
            >
              Check it on the review page
            </button>
            <button
              type="button"
              class="mt-1.5 w-full rounded-md border border-neutral-600 px-2 py-1 text-[11px] text-neutral-300"
              @click="discardDraft"
            >
              Discard the draft
            </button>
          </div>

          <div v-else-if="picked" class="rounded-lg border border-teal-400/40 bg-teal-400/5 p-3 text-center">
            <p class="text-sm text-teal-200">Slot complete ✓</p>
            <p class="mt-1 text-[10px] text-neutral-500">
              approved by you · drafted by the agent · both facts in the audit line
            </p>
            <button
              type="button"
              class="mt-2 w-full rounded-md bg-neutral-50 px-2 py-1.5 text-[11px] font-medium text-neutral-900"
              @click="view = 'project'"
            >
              Back to the debrief
            </button>
          </div>
        </div>

        <div class="border-t border-edge-strong p-3">
          <button type="button" class="w-full rounded-md border border-neutral-600 px-3 py-1.5 text-xs text-neutral-300">
            Open review
          </button>
        </div>
      </aside>
    </div>

    <!-- toasts -->
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
        <span class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">prototype</span>
        <button
          v-if="!morning"
          type="button"
          class="rounded-md bg-neutral-50 px-3 py-1 text-xs font-medium text-neutral-900 disabled:opacity-50"
          :disabled="!!overnight"
          @click="nextMorning"
        >
          ☾ Next morning
        </button>
        <span v-else class="text-[11px] text-neutral-500">day 2 · the work moved — look at the cards</span>
        <label class="flex cursor-pointer items-center gap-1.5 text-[11px] text-neutral-400">
          <input v-model="showNew" type="checkbox" class="accent-amber-400" />
          highlight what's new
        </label>
        <button type="button" class="ml-3 text-[11px] text-neutral-400 hover:text-neutral-100" @click="reset">
          Reset
        </button>
      </div>
    </div>
  </div>
</template>
