<script>
import { mapActions, mapState } from 'pinia'

import AnnotatedImage from '@/components/AnnotatedImage.vue'
import DefectThread from '@/components/DefectThread.vue'
import DismissalLog from '@/components/DismissalLog.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { CATEGORIES, SEVERITY_ORDER, filterDefects, isClear, sortDefects } from '@/domain/defects'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'

export default {
  name: 'ReviewPage',
  components: { AnnotatedImage, DefectThread, DismissalLog, SeverityChip },
  props: {
    projectId: { type: String, required: true },
    imageId: { type: String, required: true },
  },
  data() {
    return {
      selectedId: '',
      severities: [],
      categories: [],
      showOpenOnly: false,
      notice: '',
      versions: [],
      allSeverities: SEVERITY_ORDER,
      allCategories: CATEGORIES,
    }
  },
  computed: {
    ...mapState(useReviewStore, [
      'activeImage',
      'thread',
      'activeSummary',
      'uploading',
      'dismissals',
    ]),
    canSubmitFix() {
      return useProjectsStore().can('submit_fix')
    },
    defects() {
      return sortDefects(this.activeImage?.defects || [])
    },
    visibleDefects() {
      const filtered = filterDefects(this.defects, {
        severities: this.severities,
        categories: this.categories,
      })
      return this.showOpenOnly
        ? filtered.filter((d) => ['open', 'needs_human_review'].includes(d.status))
        : filtered
    },
    canApprove() {
      return useProjectsStore().can('approve_image')
    },
    canPropose() {
      return useProjectsStore().can('propose_memory_rule')
    },
    everythingClosed() {
      return isClear(this.defects)
    },
    approved() {
      return Boolean(this.activeImage?.image.approved_by)
    },
  },
  async created() {
    await this.load()
    window.addEventListener('keydown', this.onKey)
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.onKey)
  },
  watch: {
    // Version chips route to a sibling image; the component instance is reused.
    imageId() {
      this.load()
    },
  },
  methods: {
    ...mapActions(useReviewStore, [
      'fetchImage',
      'openThread',
      'comment',
      'transition',
      'proposeMemoryRule',
      'approveImage',
      'submitFix',
      'fetchVersions',
      'fetchDismissals',
    ]),
    async load() {
      this.notice = ''
      this.selectedId = ''
      await useProjectsStore().fetchOne(this.projectId)
      await this.fetchImage(this.projectId, this.imageId)
      this.versions = await this.fetchVersions(this.projectId, this.imageId)
      this.fetchDismissals(this.projectId, this.imageId)
      const first = this.defects[0]
      if (first) await this.select(first)
    },

    /** j/k and arrows step through defects without leaving the canvas. */
    onKey(event) {
      const tag = event.target.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      const list = this.visibleDefects
      if (!list.length) return

      const step = { j: 1, ArrowDown: 1, k: -1, ArrowUp: -1 }[event.key]
      if (!step) return

      event.preventDefault()
      const current = list.findIndex((defect) => defect.id === this.selectedId)
      const next = current === -1 ? 0 : (current + step + list.length) % list.length
      this.select(list[next])
      this.$refs.canvas?.centerOn?.(
        { cx: list[next].circle.cx, cy: list[next].circle.cy },
        1,
      )
    },
    async onFixSelected(files) {
      const file = files?.[0]
      if (!file) return
      try {
        const result = await this.submitFix(this.projectId, this.imageId, file)
        const count = result.submitted.length
        this.notice = count
          ? `Version ${result.version.version} uploaded. The agent is re-checking ${count} defect(s).`
          : `Version ${result.version.version} uploaded. Nothing was open to re-check.`
        this.versions = await this.fetchVersions(this.projectId, this.imageId)
      } catch (error) {
        this.notice = error.message
      }
    },
    async select(defect) {
      this.selectedId = defect.id
      await this.openThread(this.projectId, defect.id)
    },
    toggle(list, value) {
      const index = this[list].indexOf(value)
      if (index === -1) this[list].push(value)
      else this[list].splice(index, 1)
    },
    async onComment(body) {
      await this.comment(this.projectId, this.selectedId, body)
    },
    async onTransition({ to, rationale }) {
      try {
        await this.transition(this.projectId, this.selectedId, to, rationale)
        this.notice = ''
      } catch (error) {
        this.notice = error.message
      }
    },
    async onProposeMemory(description) {
      const proposal = await this.proposeMemoryRule(this.projectId, this.selectedId, description)
      this.notice = proposal.collisions.length
        ? `Proposed, but it overlaps ${proposal.collisions.length} existing rule(s) — the owner will be asked to resolve the conflict.`
        : 'Proposed. The brand owner approves it before it takes effect.'
    },
    async onApprove() {
      try {
        await this.approveImage(this.projectId, this.imageId)
        this.notice = 'Approved.'
      } catch (error) {
        this.notice = error.message
      }
    },
  },
}
</script>

<template>
  <div v-if="activeImage" class="grid h-full lg:grid-cols-[1fr_24rem]">
    <!-- Canvas -->
    <div class="overflow-y-auto p-6">
      <header class="mb-4 flex flex-wrap items-center gap-3">
        <RouterLink
          :to="{ name: 'project', params: { projectId } }"
          class="text-sm text-neutral-400 hover:text-neutral-100"
        >
          ← Back
        </RouterLink>
        <h2 class="font-semibold">{{ activeImage.image.filename }}</h2>
        <SeverityChip v-if="approved" :category="'Approved'" />

        <div class="ml-auto flex items-center gap-3 text-xs text-neutral-400">
          <span>{{ activeSummary.open }} open</span>
          <span>{{ activeSummary.inFlight }} in flight</span>
          <span>{{ activeSummary.closed }} closed</span>
        </div>
      </header>

      <!-- Filters -->
      <div class="mb-4 flex flex-wrap items-center gap-2 text-xs">
        <button
          v-for="severity in allSeverities"
          :key="severity"
          type="button"
          class="rounded-full px-2.5 py-1 ring-1 ring-inset transition"
          :class="
            severities.includes(severity)
              ? 'bg-neutral-100 text-neutral-900 ring-neutral-100'
              : 'text-neutral-400 ring-neutral-700 hover:text-neutral-100'
          "
          @click="toggle('severities', severity)"
        >
          {{ severity }}
        </button>
        <span class="mx-1 text-neutral-700">|</span>
        <button
          v-for="category in allCategories"
          :key="category"
          type="button"
          class="rounded-full px-2.5 py-1 ring-1 ring-inset transition"
          :class="
            categories.includes(category)
              ? 'bg-neutral-100 text-neutral-900 ring-neutral-100'
              : 'text-neutral-400 ring-neutral-700 hover:text-neutral-100'
          "
          @click="toggle('categories', category)"
        >
          {{ category }}
        </button>
        <label class="ml-2 flex items-center gap-1.5 text-neutral-400">
          <input v-model="showOpenOnly" type="checkbox" class="accent-neutral-100" />
          Open only
        </label>
      </div>

      <AnnotatedImage
        ref="canvas"
        :src="activeImage.original_url"
        :width="activeImage.image.width"
        :height="activeImage.image.height"
        :defects="visibleDefects"
        :selected-id="selectedId"
        @select="select"
      />

      <p v-if="notice" class="mt-3 rounded bg-neutral-800/70 p-2 text-sm text-neutral-200">
        {{ notice }}
      </p>

      <div class="mt-4 flex flex-wrap items-start gap-3">
        <label
          v-if="canSubmitFix"
          class="cursor-pointer rounded border border-neutral-600 px-4 py-2 text-sm font-medium hover:bg-neutral-800"
        >
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="hidden"
            @change="onFixSelected($event.target.files)"
          />
          {{ uploading ? 'Uploading…' : 'Submit fixed version' }}
        </label>

        <button
          v-if="canApprove"
          type="button"
          :disabled="!everythingClosed || approved"
          class="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          @click="onApprove"
        >
          {{ approved ? 'Approved' : 'Approve image' }}
        </button>
      </div>

      <p v-if="canApprove && !everythingClosed" class="mt-1.5 text-xs text-neutral-500">
        Everything must be resolved, dismissed or overridden before you can approve.
      </p>
      <p v-if="canSubmitFix" class="mt-1.5 text-xs text-neutral-500">
        Uploading a fix does not close anything by itself — the agent re-checks each open
        defect against the new version and decides.
      </p>

      <ul v-if="versions.length > 1" class="mt-4 flex flex-wrap gap-2 text-xs">
        <li v-for="entry in versions" :key="entry.id">
          <RouterLink
            :to="{ name: 'review', params: { projectId, imageId: entry.id } }"
            class="rounded-full px-2.5 py-1 ring-1 ring-inset"
            :class="
              entry.id === imageId
                ? 'bg-neutral-100 text-neutral-900 ring-neutral-100'
                : 'text-neutral-400 ring-neutral-700 hover:text-neutral-100'
            "
          >
            v{{ entry.version }}
          </RouterLink>
        </li>
      </ul>

      <!-- Defect list -->
      <ul class="mt-6 divide-y divide-neutral-800 rounded-lg border border-neutral-800">
        <li v-for="defect in visibleDefects" :key="defect.id">
          <button
            type="button"
            class="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-neutral-900"
            :class="selectedId === defect.id ? 'bg-neutral-900' : ''"
            @click="select(defect)"
          >
            <span class="mt-0.5 font-mono text-xs text-neutral-500">{{ defect.pin }}</span>
            <span class="flex-1">
              <span class="block text-sm">{{ defect.comment }}</span>
              <span class="mt-1 flex flex-wrap items-center gap-1.5">
                <SeverityChip :severity="defect.severity" />
                <SeverityChip :status="defect.status" />
                <span class="text-xs text-neutral-500">{{ defect.cells.join(', ') }}</span>
              </span>
            </span>
          </button>
        </li>
      </ul>

      <p v-if="!visibleDefects.length" class="mt-4 text-sm text-neutral-500">
        No defects match these filters.
      </p>

      <div class="mt-4">
        <DismissalLog :dismissals="dismissals" />
      </div>

      <p class="mt-3 text-xs text-neutral-600">
        <kbd class="rounded border border-neutral-700 px-1">j</kbd> /
        <kbd class="rounded border border-neutral-700 px-1">k</kbd> to step through defects ·
        scroll to zoom · drag to pan
      </p>
    </div>

    <DefectThread
      v-if="thread"
      :thread="thread"
      :can-propose="canPropose"
      @comment="onComment"
      @transition="onTransition"
      @propose-memory="onProposeMemory"
    />
  </div>

  <p v-else class="p-10 text-sm text-neutral-500">Loading…</p>
</template>
