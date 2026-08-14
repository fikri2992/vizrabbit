<script>
import { mapActions, mapState } from 'pinia'

import ActivityFeed from '@/components/ActivityFeed.vue'
import GuidelinePanel from '@/components/GuidelinePanel.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { summarize } from '@/domain/defects'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'

export default {
  name: 'ProjectPage',
  components: { ActivityFeed, GuidelinePanel, SeverityChip },
  props: { projectId: { type: String, required: true } },
  data() {
    return { dragging: false }
  },
  computed: {
    ...mapState(useProjectsStore, ['currentProject', 'currentRole']),
    ...mapState(useReviewStore, ['images', 'recentActivity', 'streaming', 'uploading', 'error']),
    canUpload() {
      return useProjectsStore().can('upload_images')
    },
    canEditGuideline() {
      return useProjectsStore().can('edit_guideline')
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
    ...mapActions(useReviewStore, ['fetchImages', 'upload', 'startStream', 'stopStream']),
    summaryOf(entry) {
      return summarize(entry.defects)
    },
    statusLabel(entry) {
      const { image, defects } = entry
      if (image.status === 'failed') return 'Failed'
      if (image.status !== 'done') return 'Reviewing…'
      const { open, blockers } = summarize(defects)
      if (image.approved_by) return 'Approved'
      if (open === 0) return 'Clear'
      return `${open} open${blockers ? `, ${blockers} blocker` : ''}`
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
  },
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-8">
    <header class="flex items-baseline justify-between">
      <div>
        <h2 class="text-xl font-semibold tracking-tight">
          {{ currentProject?.name || 'Project' }}
        </h2>
        <p class="mt-1 text-sm text-neutral-500">You are the {{ currentRole }} on this project.</p>
      </div>
      <RouterLink to="/" class="text-sm text-neutral-400 hover:text-neutral-100">
        All projects
      </RouterLink>
    </header>

    <div class="mt-6 grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div>
        <!-- Upload -->
        <label
          v-if="canUpload"
          class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition"
          :class="dragging ? 'border-neutral-400 bg-neutral-900' : 'border-neutral-700'"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
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

        <!-- Images -->
        <div v-if="images.length" class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <RouterLink
            v-for="entry in images"
            :key="entry.image.id"
            :to="{ name: 'review', params: { projectId, imageId: entry.image.id } }"
            class="group overflow-hidden rounded-lg border border-neutral-800 hover:border-neutral-600"
          >
            <img
              :src="entry.annotated_url || entry.original_url"
              :alt="entry.image.filename"
              class="aspect-square w-full object-cover"
            />
            <div class="flex items-center justify-between gap-2 px-3 py-2">
              <span class="truncate text-sm">{{ entry.image.filename }}</span>
              <SeverityChip
                :status="summaryOf(entry).blockers ? '' : ''"
                :category="statusLabel(entry)"
              />
            </div>
          </RouterLink>
        </div>

        <p v-else class="mt-8 text-sm text-neutral-500">
          No images yet. Upload a batch to begin.
        </p>
      </div>

      <div class="space-y-6">
        <ActivityFeed :events="recentActivity" :streaming="streaming" />
        <GuidelinePanel :project-id="projectId" :can-edit="canEditGuideline" />
      </div>
    </div>
  </div>
</template>
