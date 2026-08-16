<script>
import { isQuestion, parseMeasurement } from '@/domain/defects'
import { ago } from '@/domain/time'

const TRANSITION_LABELS = {
  dismissed: 'Dismiss',
  override_approved: 'Override…',
}

/**
 * The expanded body of a defect card: replies, a one-line reply box, and a
 * single row of small actions. The card above owns the header and comment —
 * nothing is repeated here.
 */
export default {
  name: 'DefectThread',
  props: {
    thread: { type: Object, required: true },
    canPropose: { type: Boolean, default: false },
  },
  emits: ['comment', 'transition', 'propose-memory', 'answer'],
  data() {
    return { body: '', rationale: '', overriding: false, memorizing: false, proposal: '' }
  },
  computed: {
    defect() {
      return this.thread.defect
    },
    transitions() {
      return this.thread.available_transitions.map((value) => ({
        value,
        label: TRANSITION_LABELS[value] || value,
      }))
    },
    /** A question, not a flag (decision 19 glossary): asked, answerable, ignorable. */
    question() {
      return isQuestion(this.defect)
    },
    /** The stamped ΔE measurement, when this is a colour question. */
    measurement() {
      return this.question ? parseMeasurement(this.defect.comment) : null
    },
  },
  methods: {
    submitComment() {
      if (!this.body.trim()) return
      this.$emit('comment', this.body)
      this.body = ''
    },
    pick(transition) {
      if (transition === 'override_approved') {
        this.overriding = !this.overriding
        this.memorizing = false
        return
      }
      this.$emit('transition', { to: transition, rationale: '' })
    },
    submitOverride() {
      if (!this.rationale.trim()) return
      this.$emit('transition', { to: 'override_approved', rationale: this.rationale })
      this.rationale = ''
      this.overriding = false
    },
    submitProposal() {
      if (!this.proposal.trim()) return
      this.$emit('propose-memory', this.proposal)
      this.proposal = ''
      this.memorizing = false
    },
    ago,
  },
}
</script>

<template>
  <div class="mt-2 border-t border-neutral-800 pt-2.5">
    <!-- A question thread: the agent asking, not flagging. Ignorable forever. -->
    <div v-if="question" class="mb-2 rounded-lg border border-violet-400/40 bg-violet-400/5 p-2.5">
      <p class="text-[10px] uppercase tracking-wide text-violet-300">
        The agent isn't sure — your eyes
      </p>
      <div v-if="measurement" class="mt-2 flex items-center gap-2.5">
        <span class="flex flex-col items-center gap-0.5">
          <span
            class="h-9 w-14 rounded ring-1 ring-inset ring-white/15"
            :style="{ background: measurement.nearestHex }"
          />
          <span class="text-[9px] text-neutral-500">brand · {{ measurement.nearestHex }}</span>
        </span>
        <span class="flex flex-col items-center gap-0.5">
          <span
            class="h-9 w-14 rounded ring-1 ring-inset ring-white/15"
            :style="{ background: measurement.hex }"
          />
          <span class="text-[9px] text-neutral-500">this · {{ measurement.hex }}</span>
        </span>
        <span class="text-[10px] leading-snug text-neutral-400">
          ΔE {{ measurement.deltaE }} apart — judge with your own eyes first
        </span>
      </div>
      <div class="mt-2 flex items-center gap-1.5">
        <button
          type="button"
          class="rounded-md bg-neutral-50 px-2.5 py-1 text-[11px] font-medium text-neutral-900"
          @click="$emit('answer', { confirmed: true })"
        >
          It's real — keep it
        </button>
        <button
          type="button"
          class="rounded-md border border-neutral-600 px-2.5 py-1 text-[11px] text-neutral-300 hover:bg-neutral-800"
          title="Dismisses the question and teaches the rule — owner only"
          @click="$emit('answer', { confirmed: false })"
        >
          Not a problem
        </button>
        <span class="ml-auto text-[10px] text-neutral-600">
          or just leave it — an unanswered question never blocks
        </span>
      </div>
    </div>

    <p v-if="!defect.circle_verified && !question" class="mb-2 text-xs text-amber-400">
      The agent could not confirm this marker after
      {{ defect.circle_iterations }} attempts — check the placement.
    </p>
    <p v-if="defect.rationale" class="mb-2 rounded bg-neutral-800/60 p-2 text-xs text-neutral-300">
      Override rationale: {{ defect.rationale }}
    </p>

    <!-- Replies -->
    <ul v-if="thread.comments.length" class="mb-2 space-y-2 border-l border-neutral-800 pl-2.5">
      <li v-for="comment in thread.comments" :key="comment.id" class="text-sm">
        <div class="flex items-baseline gap-2">
          <span class="text-xs font-medium" :class="comment.is_agent ? 'text-neutral-100' : ''">
            {{ comment.author_name }}
          </span>
          <span class="text-[10px] text-neutral-600">{{ ago(comment.created_at) }}</span>
        </div>
        <p class="mt-0.5 whitespace-pre-wrap text-neutral-300">{{ comment.body }}</p>
      </li>
    </ul>

    <div class="flex gap-2">
      <input
        v-model="body"
        placeholder="Reply… @name to notify"
        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2.5 py-1.5 text-sm outline-none focus:border-neutral-500"
        @keydown.enter.prevent="submitComment"
      />
      <button
        type="button"
        :disabled="!body.trim()"
        class="rounded border border-neutral-700 px-2.5 text-xs hover:bg-neutral-800 disabled:opacity-40"
        @click="submitComment"
      >
        Reply
      </button>
    </div>

    <!-- Actions: one small row; details unfold only on demand -->
    <div
      v-if="transitions.length || canPropose"
      class="mt-2 flex flex-wrap items-center gap-1.5"
    >
      <button
        v-for="option in transitions"
        :key="option.value"
        type="button"
        class="rounded-full border px-2.5 py-0.5 text-xs transition"
        :class="
          option.value === 'override_approved' && overriding
            ? 'border-amber-500 text-amber-300'
            : 'border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-neutral-100'
        "
        :title="
          option.value === 'dismissed'
            ? 'Reject this finding as a false positive'
            : 'Approve despite the finding — requires a logged rationale'
        "
        @click="pick(option.value)"
      >
        {{ option.label }}
      </button>

      <button
        v-if="canPropose"
        type="button"
        class="rounded-full border px-2.5 py-0.5 text-xs transition"
        :class="
          memorizing
            ? 'border-blue-500 text-blue-300'
            : 'border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-neutral-100'
        "
        title="Promote to a standing check on every future scan — the brand owner approves it"
        @click="((memorizing = !memorizing), (overriding = false))"
      >
        + Memory
      </button>

      <span
        v-if="!thread.available_transitions.length && thread.can_submit_fix"
        class="text-[11px] text-neutral-600"
        title="Defects are resolved by the agent re-checking a fixed version, never by hand"
      >
        closes via Submit fix
      </span>
    </div>

    <div v-if="overriding" class="mt-2 flex gap-2">
      <input
        v-model="rationale"
        placeholder="Why approve despite this? (required, logged)"
        class="min-w-0 flex-1 rounded border border-amber-700/60 bg-neutral-950 px-2.5 py-1.5 text-sm outline-none focus:border-amber-500"
        @keydown.enter.prevent="submitOverride"
      />
      <button
        type="button"
        :disabled="!rationale.trim()"
        class="rounded bg-amber-600/80 px-2.5 text-xs font-medium text-white disabled:opacity-40"
        @click="submitOverride"
      >
        Override
      </button>
    </div>

    <div v-if="memorizing" class="mt-2 flex gap-2">
      <input
        v-model="proposal"
        placeholder="Always check for…"
        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2.5 py-1.5 text-sm outline-none focus:border-blue-500"
        @keydown.enter.prevent="submitProposal"
      />
      <button
        type="button"
        :disabled="!proposal.trim()"
        class="rounded border border-neutral-700 px-2.5 text-xs hover:bg-neutral-800 disabled:opacity-40"
        @click="submitProposal"
      >
        Add
      </button>
    </div>
  </div>
</template>
