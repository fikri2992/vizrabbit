<script>
import api from '@/api'

// Upload a brand guideline, let the agent grill it, and record the owner's
// answers. Grilling happens here at upload time — never mid-scan, where it would
// block a run (domain-model.md decision 3).
export default {
  name: 'GuidelinePanel',
  props: {
    projectId: { type: String, required: true },
    canEdit: { type: Boolean, default: false },
  },
  data() {
    return {
      guidelines: [],
      name: '',
      rawText: '',
      busy: false,
      grillingFor: null,
      questions: [],
      answers: {},
      error: '',
      status: '',
    }
  },
  async created() {
    await this.load()
  },
  methods: {
    async load() {
      this.guidelines = await api.get(`/api/projects/${this.projectId}/guidelines`)
    },

    async readFile(file) {
      this.rawText = await file.text()
      if (!this.name) this.name = file.name.replace(/\.[^.]+$/, '')
    },

    async create() {
      if (!this.name.trim() || !this.rawText.trim()) return
      this.busy = true
      this.error = ''
      try {
        const guideline = await api.post(`/api/projects/${this.projectId}/guidelines`, {
          name: this.name.trim(),
          raw_text: this.rawText,
        })
        this.name = ''
        this.rawText = ''
        await this.load()
        await this.grill(guideline)
      } catch (error) {
        this.error = error.message
      } finally {
        this.busy = false
      }
    },

    async grill(guideline) {
      this.grillingFor = guideline
      this.questions = []
      this.answers = {}
      this.status = 'Reading the guideline for anything ambiguous…'
      try {
        const result = await api.post(
          `/api/projects/${this.projectId}/guidelines/${guideline.id}/grill`,
        )
        this.questions = result.questions
        this.status = this.questions.length
          ? 'Answer these so the scanner does not have to guess.'
          : 'Nothing ambiguous found — this guideline is ready to use.'
      } catch (error) {
        this.error = error.message
        this.status = ''
      }
    },

    async submitAnswer(question) {
      const answer = (this.answers[question.question] || '').trim()
      if (!answer) return
      await api.post(
        `/api/projects/${this.projectId}/guidelines/${this.grillingFor.id}/clarifications`,
        { question: question.question, answer },
      )
      this.questions = this.questions.filter((q) => q.question !== question.question)
      await this.load()
      if (!this.questions.length) this.status = 'All answered. The scanner uses these verbatim.'
    },
  },
}
</script>

<template>
  <section class="rounded-lg border border-neutral-800 bg-neutral-900/50">
    <header class="border-b border-neutral-800 px-4 py-2.5">
      <h3 class="text-sm font-medium">Brand guidelines</h3>
    </header>

    <div class="space-y-4 p-4">
      <ul v-if="guidelines.length" class="space-y-2">
        <li
          v-for="guideline in guidelines"
          :key="guideline.id"
          class="rounded border border-neutral-800 px-3 py-2"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-medium">{{ guideline.name }}</span>
            <button
              v-if="canEdit"
              type="button"
              class="text-xs text-neutral-400 hover:text-neutral-100"
              @click="grill(guideline)"
            >
              Re-check for gaps
            </button>
          </div>
          <p class="mt-1 text-xs text-neutral-500">
            {{ guideline.clarifications.length }} clarification(s) recorded
          </p>
        </li>
      </ul>
      <p v-else class="text-sm text-neutral-500">
        No brand guideline yet. Built-in AI-defect rules are always active regardless.
      </p>

      <!-- Upload -->
      <form v-if="canEdit" class="space-y-2 border-t border-neutral-800 pt-4" @submit.prevent="create">
        <input
          v-model="name"
          placeholder="Guideline name"
          class="w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm"
        />
        <textarea
          v-model="rawText"
          rows="4"
          placeholder="Paste the guideline text, or choose a .txt/.md file below"
          class="w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
        />
        <div class="flex items-center gap-2">
          <label class="cursor-pointer text-xs text-neutral-400 hover:text-neutral-100">
            <input
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              class="hidden"
              @change="readFile($event.target.files[0])"
            />
            Choose a file
          </label>
          <button
            type="submit"
            :disabled="busy || !name.trim() || !rawText.trim()"
            class="ml-auto rounded bg-neutral-100 px-3 py-1.5 text-sm font-medium text-neutral-900 disabled:opacity-40"
          >
            {{ busy ? 'Saving…' : 'Add and check' }}
          </button>
        </div>
      </form>

      <!-- Grilling -->
      <div v-if="status" class="border-t border-neutral-800 pt-4">
        <p class="text-xs text-neutral-400">{{ status }}</p>

        <ul class="mt-3 space-y-3">
          <li v-for="question in questions" :key="question.question">
            <p class="text-sm">{{ question.question }}</p>
            <p v-if="question.why_it_matters" class="mt-0.5 text-xs text-neutral-500">
              {{ question.why_it_matters }}
            </p>
            <div class="mt-1.5 flex gap-2">
              <input
                v-model="answers[question.question]"
                placeholder="Your answer"
                class="flex-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm"
                @keyup.enter="submitAnswer(question)"
              />
              <button
                type="button"
                :disabled="!(answers[question.question] || '').trim()"
                class="rounded border border-neutral-700 px-3 text-sm hover:bg-neutral-800 disabled:opacity-40"
                @click="submitAnswer(question)"
              >
                Save
              </button>
            </div>
          </li>
        </ul>
      </div>

      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
    </div>
  </section>
</template>
