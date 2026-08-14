<script>
import SeverityChip from '@/components/SeverityChip.vue'

const TRANSITION_LABELS = {
  fix_submitted: 'Submit a fix',
  dismissed: 'Dismiss as false positive',
  override_approved: 'Override and approve',
}

export default {
  name: 'DefectThread',
  components: { SeverityChip },
  props: {
    thread: { type: Object, required: true },
    canPropose: { type: Boolean, default: false },
  },
  emits: ['comment', 'transition', 'propose-memory'],
  data() {
    return { body: '', rationale: '', pendingTransition: '', proposal: '' }
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
    needsRationale() {
      return this.pendingTransition === 'override_approved'
    },
  },
  methods: {
    submitComment() {
      if (!this.body.trim()) return
      this.$emit('comment', this.body)
      this.body = ''
    },
    submitTransition() {
      if (!this.pendingTransition) return
      if (this.needsRationale && !this.rationale.trim()) return
      this.$emit('transition', { to: this.pendingTransition, rationale: this.rationale })
      this.pendingTransition = ''
      this.rationale = ''
    },
    submitProposal() {
      if (!this.proposal.trim()) return
      this.$emit('propose-memory', this.proposal)
      this.proposal = ''
    },
    when(value) {
      return new Date(value).toLocaleString()
    },
  },
}
</script>

<template>
  <aside class="flex h-full flex-col gap-4 overflow-y-auto border-l border-neutral-800 p-5">
    <header>
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold">Pin {{ defect.pin }}</span>
        <SeverityChip :severity="defect.severity" />
        <SeverityChip :status="defect.status" />
      </div>
      <p class="mt-2 text-sm text-neutral-200">{{ defect.comment }}</p>
      <p class="mt-1 text-xs text-neutral-500">
        {{ defect.category }} · cells {{ defect.cells.join(', ') }}
        <template v-if="defect.rule_ref"> · rule {{ defect.rule_ref }}</template>
      </p>
      <p v-if="!defect.circle_verified" class="mt-2 text-xs text-amber-400">
        The agent could not confirm this circle after
        {{ defect.circle_iterations }} attempts — check the placement.
      </p>
      <p v-if="defect.rationale" class="mt-2 rounded bg-neutral-800/60 p-2 text-xs text-neutral-300">
        Override rationale: {{ defect.rationale }}
      </p>
    </header>

    <!-- Comments -->
    <section class="flex-1">
      <h4 class="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">Thread</h4>
      <ul v-if="thread.comments.length" class="space-y-3">
        <li v-for="comment in thread.comments" :key="comment.id" class="text-sm">
          <div class="flex items-baseline gap-2">
            <span class="font-medium">{{ comment.author_name }}</span>
            <span class="text-xs text-neutral-500">{{ when(comment.created_at) }}</span>
          </div>
          <p class="mt-0.5 whitespace-pre-wrap text-neutral-300">{{ comment.body }}</p>
        </li>
      </ul>
      <p v-else class="text-sm text-neutral-500">No replies yet.</p>

      <form class="mt-3" @submit.prevent="submitComment">
        <textarea
          v-model="body"
          rows="3"
          placeholder="Reply… use @name to notify a teammate"
          class="w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm outline-none focus:border-neutral-500"
        />
        <button
          type="submit"
          :disabled="!body.trim()"
          class="mt-2 rounded bg-neutral-100 px-3 py-1.5 text-sm font-medium text-neutral-900 disabled:opacity-40"
        >
          Reply
        </button>
      </form>
    </section>

    <!-- Lifecycle -->
    <section v-if="transitions.length" class="border-t border-neutral-800 pt-4">
      <h4 class="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">Actions</h4>
      <select
        v-model="pendingTransition"
        class="w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
      >
        <option value="">Choose an action…</option>
        <option v-for="option in transitions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>

      <textarea
        v-if="needsRationale"
        v-model="rationale"
        rows="2"
        placeholder="Why are you approving this despite the finding? (required, logged)"
        class="mt-2 w-full rounded border border-amber-700/60 bg-neutral-900 p-2 text-sm"
      />

      <button
        type="button"
        :disabled="!pendingTransition || (needsRationale && !rationale.trim())"
        class="mt-2 w-full rounded bg-neutral-800 px-3 py-1.5 text-sm font-medium hover:bg-neutral-700 disabled:opacity-40"
        @click="submitTransition"
      >
        Apply
      </button>

      <p class="mt-2 text-xs text-neutral-500">
        Defects are resolved by the agent re-checking a fixed version, never by hand.
      </p>
    </section>

    <!-- Memory -->
    <section v-if="canPropose" class="border-t border-neutral-800 pt-4">
      <h4 class="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">Memory</h4>
      <input
        v-model="proposal"
        placeholder="Always check for…"
        class="w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
      />
      <button
        type="button"
        :disabled="!proposal.trim()"
        class="mt-2 w-full rounded border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-800 disabled:opacity-40"
        @click="submitProposal"
      >
        Add to memory
      </button>
      <p class="mt-2 text-xs text-neutral-500">
        Promotes this defect to a standing check on every future scan. The brand owner approves it.
      </p>
    </section>
  </aside>
</template>
