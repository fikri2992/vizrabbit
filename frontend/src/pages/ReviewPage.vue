<script>
import { mapActions, mapState } from 'pinia'

import AnnotatedImage from '@/components/AnnotatedImage.vue'
import DefectThread from '@/components/DefectThread.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { CATEGORIES, SEVERITY_ORDER, filterDefects, isClear, sortDefects } from '@/domain/defects'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'

export default {
  name: 'ReviewPage',
  components: { AnnotatedImage, DefectThread, SeverityChip },
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
      allSeverities: SEVERITY_ORDER,
      allCategories: CATEGORIES,
    }
  },
  computed: {
    ...mapState(useReviewStore, ['activeImage', 'thread', 'activeSummary']),
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
    await useProjectsStore().fetchOne(this.projectId)
    await this.fetchImage(this.projectId, this.imageId)
    const first = this.defects[0]
    if (first) this.select(first)
  },
  methods: {
    ...mapActions(useReviewStore, [
      'fetchImage',
      'openThread',
      'comment',
      'transition',
      'proposeMemoryRule',
      'approveImage',
    ]),
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

      <div v-if="canApprove" class="mt-4">
        <button
          type="button"
          :disabled="!everythingClosed || approved"
          class="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          @click="onApprove"
        >
          {{ approved ? 'Approved' : 'Approve image' }}
        </button>
        <p v-if="!everythingClosed" class="mt-1.5 text-xs text-neutral-500">
          Everything must be resolved, dismissed or overridden before you can approve.
        </p>
      </div>

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
