<script>
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
  emits: ['comment', 'transition', 'propose-memory'],
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
    <p v-if="!defect.circle_verified" class="mb-2 text-xs text-amber-400">
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
          <span class="text-xs font-medium" :class="comment.is_agent ? 'text-violet-300' : ''">
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
