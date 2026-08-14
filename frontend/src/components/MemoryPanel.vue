<script>
import api from '@/api'

// Memory rules are the differentiator: a defect caught once becomes a standing
// check on every future scan. They stay inactive until the Brand Owner approves,
// so the owner needs somewhere to actually do that.
export default {
  name: 'MemoryPanel',
  props: {
    projectId: { type: String, required: true },
    canApprove: { type: Boolean, default: false },
  },
  data() {
    return { rules: [], busy: '', error: '' }
  },
  computed: {
    pending() {
      return this.rules.filter((rule) => !rule.active)
    },
    active() {
      return this.rules.filter((rule) => rule.active)
    },
  },
  created() {
    this.load()
  },
  methods: {
    async load() {
      try {
        this.rules = await api.get(`/api/projects/${this.projectId}/memory`)
      } catch (error) {
        this.error = error.message
      }
    },
    async approve(rule) {
      this.busy = rule.id
      this.error = ''
      try {
        await api.post(`/api/projects/${this.projectId}/memory/${rule.id}/approve`)
        await this.load()
      } catch (error) {
        this.error = error.message
      } finally {
        this.busy = ''
      }
    },
    /** Rules whose wording overlaps this one — the owner should reconcile them. */
    overlaps(rule) {
      const words = (text) =>
        new Set(
          (text || '')
            .toLowerCase()
            .match(/[a-z]+/g)
            ?.filter((word) => word.length > 3) || [],
        )
      const mine = words(rule.description)
      if (!mine.size) return []
      return this.active
        .filter((other) => other.id !== rule.id)
        .filter((other) => {
          const theirs = words(other.description)
          if (!theirs.size) return false
          const shared = [...mine].filter((word) => theirs.has(word)).length
          return shared / new Set([...mine, ...theirs]).size >= 0.4
        })
    },
  },
}
</script>

<template>
  <section class="rounded-lg border border-neutral-800 bg-neutral-900/50">
    <header class="flex items-center gap-2 border-b border-neutral-800 px-4 py-2.5">
      <h3 class="text-sm font-medium">Memory rules</h3>
      <span v-if="pending.length" class="ml-auto text-xs text-amber-400">
        {{ pending.length }} awaiting approval
      </span>
    </header>

    <div class="space-y-4 p-4">
      <!-- Pending -->
      <div v-if="pending.length" class="space-y-3">
        <div
          v-for="rule in pending"
          :key="rule.id"
          class="rounded border border-amber-800/50 bg-amber-950/20 px-3 py-2.5"
        >
          <p class="text-sm">{{ rule.description }}</p>

          <p v-if="overlaps(rule).length" class="mt-1.5 text-xs text-amber-300">
            Overlaps {{ overlaps(rule).length }} active rule(s). Approving both leaves the scanner
            with two rules covering the same ground — reword one, or approve deliberately.
          </p>

          <div v-if="canApprove" class="mt-2 flex items-center gap-2">
            <button
              type="button"
              :disabled="busy === rule.id"
              class="rounded bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-900 disabled:opacity-40"
              @click="approve(rule)"
            >
              {{ busy === rule.id ? 'Approving…' : 'Approve' }}
            </button>
            <span class="text-xs text-neutral-500">Takes effect on the next scan</span>
          </div>
          <p v-else class="mt-1.5 text-xs text-neutral-500">
            Waiting on the brand owner.
          </p>
        </div>
      </div>

      <!-- Active -->
      <ul v-if="active.length" class="space-y-1.5">
        <li v-for="rule in active" :key="rule.id" class="flex gap-2 text-sm">
          <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-green-500" />
          <span class="text-neutral-300">{{ rule.description }}</span>
        </li>
      </ul>

      <p v-if="!rules.length" class="text-sm text-neutral-500">
        No memory rules yet. Use <span class="text-neutral-300">Add to memory</span> on a defect to
        make it a standing check on every future scan.
      </p>

      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
    </div>
  </section>
</template>
