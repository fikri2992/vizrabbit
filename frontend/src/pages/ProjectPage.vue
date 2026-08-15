<script>
import { mapActions, mapState } from 'pinia'

import ActivityFeed from '@/components/ActivityFeed.vue'
import GuidelinePanel from '@/components/GuidelinePanel.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'
import TeamPanel from '@/components/TeamPanel.vue'
import { summarize } from '@/domain/defects'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'

export default {
  name: 'ProjectPage',
  components: { ActivityFeed, GuidelinePanel, MemoryPanel, TeamPanel },
  props: { projectId: { type: String, required: true } },
  data() {
    return { dragging: false, confirmingId: '', deleteError: '' }
  },
  computed: {
    ...mapState(useProjectsStore, ['currentProject', 'currentRole']),
    ...mapState(useReviewStore, ['images', 'recentActivity', 'streaming', 'uploading', 'error']),
    canUpload() {
      return useProjectsStore().can('upload_images')
    },
    canDelete() {
      return useProjectsStore().can('delete_image')
    },
    canEditGuideline() {
      return useProjectsStore().can('edit_guideline')
    },
    canApproveMemory() {
      return useProjectsStore().can('approve_memory_rule')
    },
    /**
     * One card per asset: superseded versions collapse behind their newest
     * fix, with a version badge instead of a confusing duplicate card.
     */
    latestImages() {
      const superseded = new Set(
        this.images.map((entry) => entry.image.supersedes_id).filter(Boolean),
      )
      return this.images.filter((entry) => !superseded.has(entry.image.id))
    },
    needsAttention() {
      return this.latestImages.filter((entry) => this.pillOf(entry).tone === 'amber' || this.pillOf(entry).tone === 'red').length
    },
  },
  async created() {
    await useProjectsStore().fetchOne(this.projectId)
    await this.fetchImages(this.projectId)
    this.startStream(this.projectId)
  },
  beforeUnmount() {
    this.stopStream()
  },
  methods: {
    ...mapActions(useReviewStore, [
      'fetchImages',
      'upload',
      'deleteImage',
      'startStream',
      'stopStream',
    ]),

    /** What the reviewer needs to know at a glance, as label + colour. */
    pillOf(entry) {
      const { image, defects } = entry
      if (image.status === 'failed') return { label: 'Failed', tone: 'red' }
      if (image.status !== 'done') return { label: 'Reviewing…', tone: 'violet' }
      if (image.approved_by) return { label: 'Approved', tone: 'green' }
      const { open, blockers } = summarize(defects)
      if (open === 0) return { label: 'Clear', tone: 'green' }
      if (blockers) return { label: `${open} open · ${blockers} blocker`, tone: 'red' }
      return { label: `${open} open`, tone: 'amber' }
    },

    pillClass(tone) {
      return {
        green: 'bg-green-500/20 text-green-200 ring-green-500/40',
        amber: 'bg-amber-500/20 text-amber-200 ring-amber-500/40',
        red: 'bg-red-500/20 text-red-200 ring-red-500/40',
        violet: 'bg-violet-500/20 text-violet-200 ring-violet-500/40 animate-pulse',
      }[tone]
    },

    async onFiles(fileList) {
      const files = Array.from(fileList).filter((file) => file.type.startsWith('image/'))
      if (!files.length) return
      await this.upload(this.projectId, files)
    },

    onDrop(event) {
      this.dragging = false
      this.onFiles(event.dataTransfer.files)
    },

    async onDelete(entry) {
      if (this.confirmingId !== entry.image.id) {
        this.confirmingId = entry.image.id
        return
      }
      this.confirmingId = ''
      this.deleteError = ''
      try {
        await this.deleteImage(this.projectId, entry.image.id)
      } catch (error) {
        this.deleteError = error.message
      }
    },
  },
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-6">
    <!-- Header: where am I, what needs me, what can I do -->
    <RouterLink to="/" class="text-xs text-neutral-500 hover:text-neutral-200">
      ← All projects
    </RouterLink>
    <header class="mt-1 flex flex-wrap items-center gap-3">
      <h2 class="text-xl font-semibold tracking-tight">
        {{ currentProject?.name || 'Project' }}
      </h2>
      <span class="rounded-full border border-neutral-700 px-2 py-0.5 text-[11px] capitalize text-neutral-400">
        {{ currentRole }}
      </span>
      <span v-if="needsAttention" class="text-xs text-amber-300">
        {{ needsAttention }} image{{ needsAttention > 1 ? 's' : '' }} need{{ needsAttention > 1 ? '' : 's' }} review
      </span>

      <label
        v-if="canUpload && latestImages.length"
        class="ml-auto cursor-pointer rounded bg-neutral-100 px-3 py-1.5 text-sm font-medium text-neutral-900 hover:bg-white"
      >
        <input
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp"
          class="hidden"
          @change="onFiles($event.target.files)"
        />
        {{ uploading ? 'Uploading…' : 'Add images' }}
      </label>
    </header>

    <div class="mt-5 grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div
        @dragover.prevent="dragging = canUpload"
        @dragleave.prevent="dragging = false"
        @drop.prevent="canUpload && onDrop($event)"
      >
        <!-- First-run hero dropzone; once assets exist it shrinks out of the way -->
        <label
          v-if="canUpload && !latestImages.length"
          class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-14 text-center transition"
          :class="dragging ? 'border-neutral-400 bg-neutral-900' : 'border-neutral-700'"
        >
          <input
            type="file"
            multiple
            accept="image/png,image/jpeg,image/webp"
            class="hidden"
            @change="onFiles($event.target.files)"
          />
          <span class="text-sm font-medium">
            {{ uploading ? 'Uploading…' : 'Drop images here, or click to choose' }}
          </span>
          <span class="mt-1 text-xs text-neutral-500">
            PNG, JPEG or WebP. The agents start as soon as the upload lands.
          </span>
        </label>

        <p v-if="error" class="mt-3 text-sm text-red-400">{{ error }}</p>
        <p v-if="deleteError" class="mt-3 text-sm text-red-400">{{ deleteError }}</p>

        <!-- Assets -->
        <div
          v-if="latestImages.length"
          class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          :class="dragging ? 'opacity-50' : ''"
        >
          <div
            v-for="entry in latestImages"
            :key="entry.image.id"
            class="group relative overflow-hidden rounded-lg border border-neutral-800 transition hover:border-neutral-600"
            @mouseleave="confirmingId = ''"
          >
            <RouterLink
              :to="{ name: 'review', params: { projectId, imageId: entry.image.id } }"
              class="block"
            >
              <img
                :src="entry.original_url"
                :alt="entry.image.filename"
                class="aspect-square w-full object-cover"
              />
              <div class="flex items-center gap-2 px-3 py-2">
                <span class="min-w-0 truncate text-sm">{{ entry.image.filename }}</span>
                <span
                  v-if="entry.image.version > 1"
                  class="shrink-0 rounded-full border border-neutral-700 px-1.5 text-[10px] text-neutral-400"
                >
                  v{{ entry.image.version }}
                </span>
                <span
                  class="ml-auto shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset"
                  :class="pillClass(pillOf(entry).tone)"
                >
                  {{ pillOf(entry).label }}
                </span>
              </div>
            </RouterLink>

            <!-- Delete: owner-only, two clicks on purpose -->
            <button
              v-if="canDelete"
              type="button"
              class="absolute right-2 top-2 rounded-md px-2 py-1 text-xs opacity-0 shadow transition focus:opacity-100 group-hover:opacity-100"
              :class="
                confirmingId === entry.image.id
                  ? 'bg-red-600 font-medium text-white'
                  : 'bg-neutral-950/80 text-neutral-300 backdrop-blur hover:text-white'
              "
              :aria-label="confirmingId === entry.image.id ? 'Confirm delete' : `Delete ${entry.image.filename}`"
              @click.stop.prevent="onDelete(entry)"
            >
              <template v-if="confirmingId === entry.image.id">Delete image?</template>
              <svg
                v-else
                viewBox="0 0 24 24"
                class="size-3.5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <path
                  d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
        </div>

        <p v-else-if="!canUpload" class="mt-8 text-sm text-neutral-500">
          No images yet. A reviewer or the owner uploads the first batch.
        </p>
      </div>

      <div class="space-y-6">
        <ActivityFeed :events="recentActivity" :streaming="streaming" />
        <TeamPanel :project-id="projectId" />
        <MemoryPanel :project-id="projectId" :can-approve="canApproveMemory" />
        <GuidelinePanel :project-id="projectId" :can-edit="canEditGuideline" />
      </div>
    </div>
  </div>
</template>
