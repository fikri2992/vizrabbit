<script>
/**
 * PROTOTYPE — throwaway. Not wired to the API, not tested.
 *
 * Question: does the partner experience make sense when you grow into it from
 * an empty project — instead of being dropped into week-6 state?
 *
 * One linear story. Every concept (verdict, rule, spec, agenda) is born on
 * screen before anything relies on it. Mocked data; anything that would upload
 * or generate runs behind staged delays.
 */

const WAIT = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export default {
  name: 'PrototypePartnerPage',
  data() {
    return {
      stage: 0, // index into stages below
      busy: '', // current fake-latency line, '' when idle
      toasts: [],
      toastSeq: 0,

      // things that get born as the story advances
      findings: [], // stage 1
      rules: [], // stage 2+
      spec: [], // stage 3+
      agenda: [], // stage 4+
      resolvedAgenda: {},
      week6Tab: 'today',
      shareApproved: false,
    }
  },
  computed: {
    stages() {
      return [
        'A new project',
        'The first verdict',
        'Your first rule',
        'It starts noticing',
        'Six weeks later',
      ]
    },
    openFindings() {
      return this.findings.filter((finding) => !finding.done)
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
    async run(lines) {
      for (const line of lines) {
        this.busy = line
        await WAIT(1100)
      }
      this.busy = ''
    },

    // --- stage 0 → 1: the first upload ------------------------------------

    async firstUpload() {
      await this.run(['Uploading hero_draft.png…', 'Looking at it…', 'Checking against your brand PDF…'])
      this.findings = [
        {
          id: 'contrast',
          title: 'The headline is hard to read',
          detail: 'Text vs background measures 2.1:1 — your brand PDF (p.4) asks for at least 3:1.',
          source: 'from your brand PDF',
          done: false,
        },
        {
          id: 'shadow',
          title: 'The product has a drop shadow',
          detail: 'Your PDF doesn’t mention shadows either way, so I’m asking rather than deciding.',
          source: 'I’m not sure — you tell me',
          done: false,
        },
      ]
      this.stage = 1
    },

    // --- stage 1 → 2: agreeing and disagreeing both teach ------------------

    async fixFinding(finding) {
      await this.run(['Nudging the headline up to 4.8:1…', 'Re-checking…'])
      finding.done = 'Fixed — new version passed the re-check.'
      this.toast('The fix became a new version. The old one is still there — nothing is overwritten.')
      this.maybeAdvanceToRule()
    },
    dismissFinding(finding) {
      finding.done = 'You said this is fine.'
      finding.asking = true
    },
    rememberRule(finding) {
      finding.asking = false
      this.rules.push({
        id: 1,
        text: 'Drop shadows on product shots are fine for this brand',
        born: 'born just now, from your dismissal',
        cited: 0,
      })
      this.toast('Written down as rule #1. I won’t flag shadows again.')
      this.maybeAdvanceToRule()
    },
    maybeAdvanceToRule() {
      if (this.findings.every((finding) => finding.done && !finding.asking)) this.stage = 2
    },

    // --- stage 2 → 3: the second upload uses what it learned ---------------

    async secondUpload() {
      await this.run(['Uploading hero_v2_square.png…', 'Checking…', 'Applying rule #1…'])
      this.rules = this.rules.map((rule) => ({ ...rule, cited: rule.cited + 1 }))
      this.toast('Passed. It has a shadow — rule #1 says that’s fine, so I kept quiet about it.')
      await WAIT(1400)
      this.stage = 3
    },
    acceptSpec() {
      this.spec = [
        { format: '16x9', state: 'done' },
        { format: '1x1', state: 'done' },
        { format: '9x16', state: 'missing' },
      ]
      this.agenda = [
        {
          id: 'missing-916',
          title: 'This banner has no vertical (9:16) version yet',
          cite: 'you agreed the set is 16x9 + 1x1 + 9:16',
          actionLabel: 'A designer drops one in Drive — simulate',
        },
      ]
      this.toast('Noted as the definition of done for this slot. Now I can tell you what’s missing.')
    },

    // --- stage 3 → 4: the agenda earns its keep ----------------------------

    async resolveAgenda(item) {
      await this.run(['hero_9x16.png appeared in the Drive folder…', 'Reviewing it…'])
      this.spec = this.spec.map((entry) =>
        entry.format === '9x16' ? { ...entry, state: 'done' } : entry,
      )
      this.resolvedAgenda = { ...this.resolvedAgenda, [item.id]: 'Arrived via Drive · reviewed · clean' }
      this.toast('Nobody clicked upload — the folder you already use is the doorway.')
      await WAIT(1600)
      this.stage = 4
      this.seedWeekSix()
    },

    // --- stage 4: the mature state, now legible ----------------------------

    seedWeekSix() {
      this.rules = [
        { id: 1, text: 'Drop shadows on product shots are fine', born: 'from your dismissal, day 1', cited: 14 },
        { id: 2, text: 'Headline contrast at least 3:1', born: 'from your brand PDF, day 1', cited: 31 },
        { id: 3, text: 'Logo stays off busy photo backgrounds', born: 'from 3 rejections in week 2', cited: 9 },
      ]
      this.agenda = [
        {
          id: 'w6-stall',
          title: 'A fix has been stuck on Maya for 4 days',
          cite: 'requested Tuesday · nothing uploaded since',
          actionLabel: 'Send a reminder',
          quick: true,
        },
        {
          id: 'w6-pick',
          title: 'Two versions are clean — pick one and this slot is done',
          cite: 'both passed every check · only your approval is missing',
          actionLabel: 'Open the slot',
          quick: true,
        },
      ]
      this.resolvedAgenda = {}
    },
    quickResolve(item) {
      this.resolvedAgenda = { ...this.resolvedAgenda, [item.id]: 'Done.' }
    },
    approveShare() {
      this.busy = 'Recording the approval…'
      setTimeout(() => {
        this.busy = ''
        this.shareApproved = true
      }, 900)
    },

    reset() {
      Object.assign(this.$data, {
        stage: 0,
        busy: '',
        findings: [],
        rules: [],
        spec: [],
        agenda: [],
        resolvedAgenda: {},
        week6Tab: 'today',
        shareApproved: false,
      })
    },
  },
}
</script>

<template>
  <div class="min-h-[calc(100vh-49px)] pb-24">
    <div class="mx-auto max-w-xl px-6 py-10">
      <!-- ═══ STAGE 0: empty, honestly ═══ -->
      <template v-if="stage === 0">
        <h2 class="text-lg font-medium text-neutral-50">Autumn Drop 04</h2>
        <p class="mt-1 text-sm text-neutral-500">
          A new project. There are no rules yet, no checklist, no agenda — because you
          haven't shown me anything.
        </p>
        <div class="mt-6 rounded-xl border-2 border-dashed border-edge-strong p-10 text-center">
          <p class="text-sm text-neutral-300">Drop your first image here</p>
          <p class="mt-1 text-xs text-neutral-600">
            I'll check it against your brand PDF, and ask when I'm not sure.
          </p>
          <button
            type="button"
            class="mt-4 rounded-md bg-neutral-50 px-4 py-1.5 text-sm font-medium text-neutral-900 hover:bg-white disabled:opacity-50"
            :disabled="!!busy"
            @click="firstUpload"
          >
            Upload hero_draft.png
          </button>
        </div>
        <p class="mt-3 text-center text-[11px] text-neutral-600">
          brand PDF already imported · Drive folder /Autumn Drop connected
        </p>
      </template>

      <!-- ═══ STAGE 1: the first verdict — sources named, one is a question ═══ -->
      <template v-else-if="stage === 1">
        <h2 class="text-lg font-medium text-neutral-50">I looked at hero_draft.png</h2>
        <p class="mt-1 text-sm text-neutral-500">
          Two things. For each one I say <em>why</em>, and where the reason comes from.
        </p>
        <div class="mt-5 space-y-3">
          <div
            v-for="finding in findings"
            :key="finding.id"
            class="rounded-xl border border-edge-strong bg-panel p-4"
            :class="finding.done ? 'opacity-70' : ''"
          >
            <p class="text-sm text-neutral-100">{{ finding.title }}</p>
            <p class="mt-1 text-xs leading-relaxed text-neutral-400">{{ finding.detail }}</p>
            <p class="mt-1 text-[10px] text-neutral-600">reason: {{ finding.source }}</p>

            <div v-if="finding.asking" class="mt-3 rounded-lg bg-panel-2 p-3">
              <p class="text-xs text-neutral-200">
                Should I remember that? — "shadows on product shots are fine for this brand"
              </p>
              <div class="mt-2 flex gap-1.5">
                <button
                  type="button"
                  class="rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900"
                  @click="rememberRule(finding)"
                >
                  Yes, remember it
                </button>
                <button
                  type="button"
                  class="rounded-md border border-neutral-600 px-2.5 py-1 text-[11px] text-neutral-300"
                  @click="finding.asking = false; maybeAdvanceToRule()"
                >
                  Just this once
                </button>
              </div>
            </div>
            <div v-else-if="finding.done" class="mt-2 text-[11px] text-teal-200/90">
              ✓ {{ finding.done }}
            </div>
            <div v-else class="mt-3 flex gap-1.5">
              <button
                type="button"
                class="rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900 disabled:opacity-50"
                :disabled="!!busy"
                @click="fixFinding(finding)"
              >
                Fix it for me
              </button>
              <button
                type="button"
                class="rounded-md border border-neutral-600 px-2.5 py-1 text-[11px] text-neutral-300"
                @click="dismissFinding(finding)"
              >
                That's not a problem
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ STAGE 2: the rulebook exists now, with one entry you created ═══ -->
      <template v-else-if="stage === 2">
        <h2 class="text-lg font-medium text-neutral-50">You just taught me something</h2>
        <p class="mt-1 text-sm text-neutral-500">
          Your dismissal became a rule. This is the whole rulebook so far — it only ever
          grows from moments like that one, or from your brand PDF.
        </p>
        <div class="mt-5 space-y-2">
          <div
            v-for="rule in rules"
            :key="rule.id"
            class="rounded-xl border border-edge-strong bg-panel p-3.5"
          >
            <div class="flex items-baseline gap-2">
              <span class="font-mono text-[11px] text-neutral-500">#{{ rule.id }}</span>
              <span class="text-sm text-neutral-100">{{ rule.text }}</span>
            </div>
            <p class="mt-1 text-[10px] text-neutral-600">{{ rule.born }}</p>
          </div>
        </div>
        <button
          type="button"
          class="mt-6 w-full rounded-md bg-neutral-50 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:opacity-50"
          :disabled="!!busy"
          @click="secondUpload"
        >
          Upload the next image and see the rule at work
        </button>
      </template>

      <!-- ═══ STAGE 3: spec proposed from behavior, agenda born from spec ═══ -->
      <template v-else-if="stage === 3">
        <h2 class="text-lg font-medium text-neutral-50">It passed — and I noticed a pattern</h2>
        <p class="mt-1 text-sm text-neutral-500">
          You've now made a wide and a square version of this banner. Campaigns like this
          usually ship a vertical too.
        </p>

        <div v-if="!spec.length" class="mt-5 rounded-xl border border-edge-strong bg-panel p-4">
          <p class="text-sm text-neutral-100">
            Should "16x9 + 1x1 + 9:16" be the definition of done for this banner?
          </p>
          <p class="mt-1 text-xs text-neutral-500">
            If yes, I can tell you what's missing — instead of waiting for you to remember.
          </p>
          <div class="mt-3 flex gap-1.5">
            <button
              type="button"
              class="rounded-md bg-neutral-50 px-3 py-1 text-[11px] font-medium text-neutral-900"
              @click="acceptSpec"
            >
              Yes, that's the set
            </button>
            <button
              type="button"
              class="rounded-md border border-neutral-600 px-3 py-1 text-[11px] text-neutral-300"
            >
              No, just these two
            </button>
          </div>
        </div>

        <template v-else>
          <div class="mt-5 flex gap-2">
            <span
              v-for="entry in spec"
              :key="entry.format"
              class="flex items-center gap-1.5 rounded-full border border-edge-strong px-2.5 py-1 text-[11px] text-neutral-300"
            >
              <span
                class="size-1.5 rounded-full"
                :style="{ background: entry.state === 'done' ? '#9FE1CB' : '#FAC775' }"
              />
              {{ entry.format }}
            </span>
          </div>
          <div class="mt-4 space-y-2.5">
            <div
              v-for="item in agenda"
              :key="item.id"
              class="rounded-xl border border-edge-strong bg-panel p-4"
            >
              <p class="text-sm text-neutral-100">{{ item.title }}</p>
              <p class="mt-1 text-[11px] text-neutral-500">because: {{ item.cite }}</p>
              <div v-if="resolvedAgenda[item.id]" class="mt-2 text-[11px] text-teal-200/90">
                ✓ {{ resolvedAgenda[item.id] }}
              </div>
              <button
                v-else
                type="button"
                class="mt-2.5 rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900 disabled:opacity-50"
                :disabled="!!busy"
                @click="resolveAgenda(item)"
              >
                {{ item.actionLabel }}
              </button>
            </div>
          </div>
        </template>
      </template>

      <!-- ═══ STAGE 4: week 6 — the screen from before, now earned ═══ -->
      <template v-else>
        <h2 class="text-lg font-medium text-neutral-50">Six weeks later</h2>
        <p class="mt-1 text-sm text-neutral-500">
          Everything below grew exactly the way you just watched: rules from your calls,
          the checklist from your patterns, the to-do list from the gaps.
        </p>

        <div class="mt-4 flex gap-1">
          <button
            v-for="tab in [
              { id: 'today', label: 'To-do' },
              { id: 'rules', label: 'Rulebook' },
              { id: 'share', label: 'Client link' },
            ]"
            :key="tab.id"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs"
            :class="
              week6Tab === tab.id
                ? 'bg-neutral-50 font-medium text-neutral-900'
                : 'text-neutral-400 hover:bg-edge'
            "
            @click="week6Tab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>

        <div v-if="week6Tab === 'today'" class="mt-4 space-y-2.5">
          <div
            v-for="item in agenda"
            :key="item.id"
            class="rounded-xl border border-edge-strong bg-panel p-4"
            :class="resolvedAgenda[item.id] ? 'opacity-60' : ''"
          >
            <p class="text-sm text-neutral-100">{{ item.title }}</p>
            <p class="mt-1 text-[11px] text-neutral-500">because: {{ item.cite }}</p>
            <div v-if="resolvedAgenda[item.id]" class="mt-2 text-[11px] text-teal-200/90">✓ Done</div>
            <button
              v-else
              type="button"
              class="mt-2.5 rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900"
              @click="quickResolve(item)"
            >
              {{ item.actionLabel }}
            </button>
          </div>
        </div>

        <div v-else-if="week6Tab === 'rules'" class="mt-4 space-y-2">
          <div
            v-for="rule in rules"
            :key="rule.id"
            class="rounded-xl border border-edge-strong bg-panel p-3.5"
          >
            <div class="flex items-baseline gap-2">
              <span class="font-mono text-[11px] text-neutral-500">#{{ rule.id }}</span>
              <span class="min-w-0 flex-1 text-sm text-neutral-100">{{ rule.text }}</span>
              <span class="text-[10px] text-neutral-600">used {{ rule.cited }}×</span>
            </div>
            <p class="mt-1 text-[10px] text-neutral-600">{{ rule.born }}</p>
          </div>
          <p class="pt-1 text-center text-[11px] text-neutral-600">
            you never filled in a settings form — every rule has a birthday and a reason
          </p>
        </div>

        <div v-else class="mt-6">
          <p class="mb-3 text-center text-[10px] uppercase tracking-widest text-neutral-600">
            what your client sees — one link, no account
          </p>
          <div class="mx-auto max-w-sm rounded-2xl border border-edge-strong bg-panel p-5 shadow-2xl shadow-black/50">
            <div class="h-44 rounded-lg" style="background: #3b5a8a" />
            <p class="mt-3 text-sm font-medium text-neutral-100">Hero banner · final</p>
            <p class="mt-2 rounded-lg bg-panel-2 p-2.5 text-[11px] text-neutral-300">
              Checked: brand colours, contrast, platform crops — nothing outstanding.
            </p>
            <button
              v-if="!shareApproved"
              type="button"
              class="mt-3 w-full rounded-lg bg-neutral-50 py-2 text-sm font-medium text-neutral-900 disabled:opacity-50"
              :disabled="!!busy"
              @click="approveShare"
            >
              Approve for release
            </button>
            <div v-else class="mt-3 rounded-lg border border-teal-400/40 bg-teal-400/5 p-3 text-center">
              <p class="text-sm text-teal-200">Approved ✓</p>
              <p class="mt-1 text-[10px] text-neutral-500">
                who approved what, over which alternatives — saved forever
              </p>
            </div>
          </div>
        </div>
      </template>

      <!-- fake-latency line -->
      <div
        v-if="busy"
        class="mt-5 flex items-center gap-2 rounded-lg border border-edge-strong bg-panel-2 px-3 py-2"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-teal-300" />
        <span class="text-xs text-neutral-300">{{ busy }}</span>
      </div>
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

    <!-- story progress -->
    <div class="fixed bottom-0 left-0 right-0 z-30 border-t border-edge-strong bg-ink/90 px-6 py-2.5 backdrop-blur">
      <div class="flex items-center justify-center gap-3">
        <span class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">
          prototype
        </span>
        <div class="flex items-center gap-2">
          <template v-for="(title, index) in stages" :key="title">
            <span
              class="text-[11px]"
              :class="index === stage ? 'font-medium text-neutral-50' : 'text-neutral-600'"
            >{{ title }}</span>
            <span v-if="index < stages.length - 1" class="text-neutral-700">→</span>
          </template>
        </div>
        <button
          type="button"
          class="ml-3 text-[11px] text-neutral-400 hover:text-neutral-100"
          @click="reset"
        >
          Start over
        </button>
      </div>
    </div>
  </div>
</template>
