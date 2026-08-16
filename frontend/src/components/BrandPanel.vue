<script>
import api from '@/api'

/**
 * The brand palette: propose, edit, confirm.
 *
 * The panel is built around one asymmetry — extraction fills the form in, and
 * nothing it proposes has any effect until the Owner presses Confirm. So the
 * proposal always renders as an editable draft, never as a live setting, and the
 * inactive state says plainly that no brand defects can be raised yet.
 */
export default {
  name: 'BrandPanel',
  props: {
    projectId: { type: String, required: true },
    canConfirm: { type: Boolean, default: false },
    canExtract: { type: Boolean, default: false },
  },
  data() {
    return {
      profile: null,
      active: false,
      draft: [], // [{ hex, role, tolerance }] — what Confirm would send
      questions: [],
      busy: false,
      error: '',
      status: '',
    }
  },
  computed: {
    /** Only well-formed hexes can be confirmed; the rest are flagged inline. */
    invalid() {
      return this.draft.filter((entry) => !/^#[0-9a-fA-F]{6}$/.test(entry.hex.trim()))
    },
    canSubmit() {
      return this.draft.length > 0 && this.invalid.length === 0 && !this.busy
    },
    dirty() {
      const live = JSON.stringify(this.profile?.entries || [])
      return JSON.stringify(this.draft) !== live
    },
  },
  async created() {
    await this.load()
  },
  methods: {
    async load() {
      const view = await api.get(`/api/projects/${this.projectId}/brand`)
      this.apply(view)
      // An unconfirmed extraction is exactly what the form should open on.
      if (!this.draft.length && this.profile.proposed.length) {
        this.draft = this.profile.proposed.map((entry) => ({ ...entry }))
      }
    },

    apply(view) {
      this.profile = view.profile
      this.active = view.active
      this.questions = view.questions || []
      this.draft = view.profile.entries.map((entry) => ({ ...entry }))
    },

    async extract(file) {
      this.busy = true
      this.error = ''
      this.status = ''
      try {
        const form = new FormData()
        form.append('file', file)
        const response = await fetch(`/api/projects/${this.projectId}/brand/extract`, {
          method: 'POST',
          credentials: 'include',
          body: form,
        })
        if (!response.ok) throw new Error(await response.text())
        const view = await response.json()
        this.profile = view.profile
        this.active = view.active
        this.questions = view.questions || []
        this.draft = view.profile.proposed.map((entry) => ({ ...entry }))
        this.status = this.draft.length
          ? `Read ${this.draft.length} colour(s). Check them, then confirm.`
          : 'No palette found in that document. Add the colours by hand.'
      } catch (error) {
        this.error = error.message
      } finally {
        this.busy = false
      }
    },

    addColour() {
      this.draft.push({ hex: '#', role: '', tolerance: 3 })
    },

    remove(index) {
      this.draft.splice(index, 1)
    },

    async confirm() {
      this.busy = true
      this.error = ''
      this.status = ''
      try {
        const view = await api.post(`/api/projects/${this.projectId}/brand/confirm`, {
          entries: this.draft.map((entry) => ({
            hex: entry.hex.trim().toLowerCase(),
            role: entry.role || '',
            tolerance: Number(entry.tolerance) || 3,
          })),
        })
        this.apply(view)
        this.status = 'Confirmed. Brand defects will be raised from the next run.'
      } catch (error) {
        this.error = error.message
      } finally {
        this.busy = false
      }
    },

    async withdraw() {
      this.busy = true
      this.error = ''
      try {
        const view = await api.post(`/api/projects/${this.projectId}/brand/withdraw`)
        this.apply(view)
        this.draft = view.profile.proposed.map((entry) => ({ ...entry }))
        this.status = 'Palette withdrawn. No brand defects will be raised.'
      } catch (error) {
        this.error = error.message
      } finally {
        this.busy = false
      }
    },
  },
}
</script>

<template>
  <section class="rounded-lg border border-edge bg-panel p-4">
    <header class="flex flex-wrap items-center gap-2">
      <h3 class="text-sm font-medium">Brand palette</h3>
      <span
        class="flex items-center gap-1.5 rounded-full border border-edge-strong px-2 py-0.5 text-[11px]"
        :class="active ? 'text-teal-300' : 'text-neutral-500'"
      >
        <span
          class="size-1.5 rounded-full"
          :style="{ background: active ? '#9FE1CB' : '#5F5E5A' }"
        />
        {{ active ? 'Enforced' : 'Not enforced' }}
      </span>
      <label
        v-if="canExtract"
        class="ml-auto cursor-pointer rounded-md border border-edge-strong px-2.5 py-1 text-[11px] text-neutral-300 hover:bg-edge"
      >
        <input
          type="file"
          accept="application/pdf"
          class="hidden"
          @change="$event.target.files[0] && extract($event.target.files[0])"
        />
        {{ busy ? 'Reading…' : 'Read from PDF…' }}
      </label>
    </header>

    <p v-if="!active" class="mt-2 text-xs leading-relaxed text-neutral-500">
      No confirmed palette, so no brand defects can be raised. Colours read from a
      guideline are a proposal until you confirm them.
    </p>
    <p v-else class="mt-2 text-xs text-neutral-500">
      Every image is measured against these colours. A region further than its
      tolerance is put to the agent, which decides whether it is a designed
      element or scene content.
    </p>

    <ul v-if="questions.length" class="mt-3 space-y-1.5 rounded-md bg-warning/10 p-2.5">
      <li class="text-[11px] font-medium text-warning">
        The document left {{ questions.length }} thing(s) unclear:
      </li>
      <li
        v-for="(question, index) in questions"
        :key="index"
        class="text-[11px] leading-relaxed text-neutral-300"
      >
        {{ question.question }}
      </li>
    </ul>

    <div v-if="draft.length" class="mt-3 space-y-1.5">
      <div
        v-for="(entry, index) in draft"
        :key="index"
        class="flex items-center gap-2"
      >
        <span
          class="size-6 shrink-0 rounded border border-edge-strong"
          :style="{ background: /^#[0-9a-fA-F]{6}$/.test(entry.hex.trim()) ? entry.hex : 'transparent' }"
        />
        <input
          v-model="entry.hex"
          type="text"
          spellcheck="false"
          placeholder="#1d9e75"
          class="w-24 rounded border bg-panel-2 px-2 py-1 font-mono text-xs text-neutral-100 outline-none focus:border-neutral-500"
          :class="/^#[0-9a-fA-F]{6}$/.test(entry.hex.trim()) ? 'border-edge-strong' : 'border-blocker'"
          :disabled="!canConfirm"
        />
        <input
          v-model="entry.role"
          type="text"
          placeholder="role"
          class="w-24 rounded border border-edge-strong bg-panel-2 px-2 py-1 text-xs text-neutral-100 outline-none focus:border-neutral-500"
          :disabled="!canConfirm"
        />
        <label class="flex items-center gap-1 text-[11px] text-neutral-500">
          ΔE
          <input
            v-model.number="entry.tolerance"
            type="number"
            min="0"
            max="100"
            step="0.5"
            class="w-14 rounded border border-edge-strong bg-panel-2 px-1.5 py-1 text-xs text-neutral-100 outline-none focus:border-neutral-500"
            :disabled="!canConfirm"
          />
        </label>
        <button
          v-if="canConfirm"
          type="button"
          class="ml-auto text-xs text-neutral-600 hover:text-blocker"
          aria-label="Remove colour"
          @click="remove(index)"
        >
          ✕
        </button>
      </div>
    </div>

    <p v-else class="mt-3 text-xs text-neutral-600">
      No colours yet. Read a guideline PDF, or add them by hand.
    </p>

    <p v-if="invalid.length" class="mt-2 text-[11px] text-blocker">
      {{ invalid.length }} colour(s) are not six-digit hex.
    </p>
    <p v-if="error" class="mt-2 text-xs text-blocker">{{ error }}</p>
    <p v-if="status" class="mt-2 text-xs text-teal-300">{{ status }}</p>

    <div v-if="canConfirm" class="mt-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="rounded-md border border-edge-strong px-2.5 py-1 text-[11px] text-neutral-300 hover:bg-edge"
        @click="addColour"
      >
        Add colour
      </button>
      <button
        type="button"
        :disabled="!canSubmit"
        class="rounded-md bg-neutral-50 px-3 py-1 text-[11px] font-medium text-neutral-900 hover:bg-white disabled:opacity-40"
        @click="confirm"
      >
        {{ active && !dirty ? 'Confirmed' : 'Confirm palette' }}
      </button>
      <button
        v-if="active"
        type="button"
        class="ml-auto text-[11px] text-neutral-500 hover:text-neutral-300"
        @click="withdraw"
      >
        Stop enforcing
      </button>
    </div>
  </section>
</template>
