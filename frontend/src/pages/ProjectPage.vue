<script>
import { mapActions, mapState } from 'pinia'

import ActivityFeed from '@/components/ActivityFeed.vue'
import GuidelinePanel from '@/components/GuidelinePanel.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'
import TeamPanel from '@/components/TeamPanel.vue'
import { summarize } from '@/domain/defects'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'

const IN_FLIGHT = ['queued', 'scanning', 'reviewing']

export default {
  name: 'ProjectPage',
  components: { ActivityFeed, GuidelinePanel, MemoryPanel, TeamPanel },
  props: { projectId: { type: String, required: true } },
  data() {
    return {
      tab: 'assets',
      dragging: false,
      menuId: '',
      deleting: null, // { entry, preview } while the modal is open
      deleteBusy: false,
      deleteError: '',
    }
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
    /** One card per asset — superseded versions collapse behind their newest fix. */
    latestImages() {
      const superseded = new Set(
        this.images.map((entry) => entry.image.supersedes_id).filter(Boolean),
      )
      return this.images.filter((entry) => !superseded.has(entry.image.id))
    },
    needsAttention() {
      return this.latestImages.filter((entry) =>
        ['amber', 'red'].includes(this.pillOf(entry).tone),
      ).length
    },
    running() {
      return this.latestImages.filter((entry) => IN_FLIGHT.includes(entry.image.status)).length
    },
    lastActivityLine() {
      const last = this.recentActivity[0]
      return last ? `${last.stage.replaceAll('_', ' ')}${last.detail ? ` — ${last.detail}` : ''}` : ''
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
      'deletePreview',
      'startStream',
      'stopStream',
    ]),

    /** What the reviewer needs to know at a glance: label + dot colour. */
    pillOf(entry) {
      const { image, defects } = entry
      if (image.status === 'failed') return { label: 'Failed', dot: '#F09595', tone: 'red' }
      if (image.status !== 'done') return { label: 'Reviewing…', dot: '#a3a3a8', tone: 'busy' }
      if (image.approved_by) return { label: 'Approved', dot: '#9FE1CB', tone: 'green' }
      const { open, blockers } = summarize(defects)
      if (open === 0) return { label: 'Clear', dot: '#9FE1CB', tone: 'green' }
      if (blockers) return { label: `${open} open · ${blockers} blocker`, dot: '#F09595', tone: 'red' }
      return { label: `${open} open`, dot: '#FAC775', tone: 'amber' }
    },

    async onFiles(fileList) {
      const files = Array.from(fileList).filter((file) => file.type.startsWith('image/'))
      if (!files.length) return
      const run = await this.upload(this.projectId, files)
      // Straight into review — the agent works alongside, not in front of, the user.
      const first = run?.image_ids?.[0]
      if (first) {
        this.$router.push({ name: 'review', params: { projectId: this.projectId, imageId: first } })
      }
    },

    onDrop(event) {
      this.dragging = false
      this.onFiles(event.dataTransfer.files)
    },

    /** Opening the modal fetches what would actually be destroyed. */
    async askDelete(entry) {
      this.menuId = ''
      this.deleteError = ''
      this.deleting = { entry, preview: null }
      try {
        this.deleting.preview = await this.deletePreview(this.projectId, entry.image.id)
      } catch (error) {
        this.deleteError = error.message
      }
    },

    async confirmDelete() {
      if (!this.deleting) return
      this.deleteBusy = true
      this.deleteError = ''
      try {
        await this.deleteImage(this.projectId, this.deleting.entry.image.id)
        this.deleting = null
      } catch (error) {
        this.deleteError = error.message
      } finally {
        this.deleteBusy = false
      }
    },
  },
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-6">
    <RouterLink to="/" class="text-xs text-neutral-500 hover:text-neutral-200">
      ← All projects
    </RouterLink>

    <header class="mt-1 flex flex-wrap items-center gap-3">
      <h2 class="text-xl font-medium tracking-tight">
        {{ currentProject?.name || 'Project' }}
      </h2>
      <span class="rounded-full border border-edge-strong px-2 py-0.5 text-[11px] capitalize text-neutral-400">
        {{ currentRole }}
      </span>
      <span v-if="needsAttention" class="text-xs text-warning">
        {{ needsAttention }} image{{ needsAttention > 1 ? 's' : '' }} need{{ needsAttention > 1 ? '' : 's' }} review
      </span>

      <label
        v-if="canUpload && tab === 'assets' && latestImages.length"
        class="ml-auto cursor-pointer rounded-md bg-neutral-50 px-3 py-1.5 text-sm font-medium text-neutral-900 hover:bg-white"
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

    <!-- Tabs: daily work first, setup chores out of the way -->
    <nav class="mt-4 flex gap-5 border-b border-edge text-sm">
      <button
        v-for="entry in [
          { id: 'assets', label: `Assets ${latestImages.length || ''}` },
          { id: 'activity', label: 'Activity' },
          { id: 'settings', label: 'Settings' },
        ]"
        :key="entry.id"
        type="button"
        class="-mb-px border-b-2 pb-2.5 transition"
        :class="
          tab === entry.id
            ? 'border-neutral-100 font-medium text-neutral-100'
            : 'border-transparent text-neutral-500 hover:text-neutral-300'
        "
        @click="tab = entry.id"
      >
        {{ entry.label }}
      </button>
    </nav>

    <!-- Assets -->
    <div
      v-if="tab === 'assets'"
      class="mt-5"
      @dragover.prevent="dragging = canUpload"
      @dragleave.prevent="dragging = false"
      @drop.prevent="canUpload && onDrop($event)"
    >
      <div
        v-if="running"
        class="mb-4 flex items-center gap-2.5 rounded-md border border-edge px-3 py-2"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-teal-300" />
        <span class="text-xs text-neutral-400">
          Agent working on {{ running }} image{{ running > 1 ? 's' : '' }}
          <template v-if="lastActivityLine"> · {{ lastActivityLine }}</template>
        </span>
        <button
          type="button"
          class="ml-auto text-xs text-neutral-500 hover:text-neutral-200"
          @click="tab = 'activity'"
        >
          Watch
        </button>
      </div>

      <label
        v-if="canUpload && !latestImages.length"
        class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-14 text-center transition"
        :class="dragging ? 'border-neutral-400 bg-panel' : 'border-edge-strong'"
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

      <p v-if="error" class="mb-3 text-sm text-blocker">{{ error }}</p>

      <div
        v-if="latestImages.length"
        class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        :class="dragging ? 'opacity-50' : ''"
      >
        <div
          v-for="entry in latestImages"
          :key="entry.image.id"
          class="group relative overflow-hidden rounded-lg border border-edge bg-panel transition hover:border-edge-strong"
          @mouseleave="menuId = ''"
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
            <div class="flex items-center gap-2 px-3 py-2.5">
              <span class="min-w-0 truncate text-sm text-neutral-200">
                {{ entry.image.filename }}
              </span>
              <span
                v-if="entry.image.version > 1"
                class="shrink-0 rounded-full border border-edge-strong px-1.5 text-[10px] text-neutral-500"
              >
                v{{ entry.image.version }}
              </span>
              <span class="ml-auto flex shrink-0 items-center gap-1.5 text-[11px] text-neutral-400">
                <span
                  class="size-1.5 rounded-full"
                  :class="pillOf(entry).tone === 'busy' ? 'animate-pulse' : ''"
                  :style="{ background: pillOf(entry).dot }"
                />
                {{ pillOf(entry).label }}
              </span>
            </div>
          </RouterLink>

          <div v-if="canDelete" class="absolute right-2 top-2">
            <button
              type="button"
              class="rounded-md bg-ink/80 px-2 py-0.5 text-sm text-neutral-300 opacity-0 backdrop-blur transition focus:opacity-100 group-hover:opacity-100 hover:text-white"
              aria-label="Image actions"
              @click.stop.prevent="menuId = menuId === entry.image.id ? '' : entry.image.id"
            >
              ⋯
            </button>
            <div
              v-if="menuId === entry.image.id"
              class="absolute right-0 mt-1 w-40 overflow-hidden rounded-md border border-edge-strong bg-panel-2 py-1 text-sm shadow-xl"
            >
              <RouterLink
                :to="{ name: 'review', params: { projectId, imageId: entry.image.id } }"
                class="block px-3 py-1.5 text-neutral-300 hover:bg-edge hover:text-white"
              >
                Open review
              </RouterLink>
              <button
                type="button"
                class="block w-full px-3 py-1.5 text-left text-blocker hover:bg-edge"
                @click.stop.prevent="askDelete(entry)"
              >
                Delete image…
              </button>
            </div>
          </div>
        </div>
      </div>

      <p v-else-if="!canUpload" class="mt-8 text-sm text-neutral-500">
        No images yet. A reviewer or the owner uploads the first batch.
      </p>
    </div>

    <!-- Activity -->
    <div v-else-if="tab === 'activity'" class="mt-5 max-w-2xl">
      <ActivityFeed :events="recentActivity" :streaming="streaming" />
    </div>

    <!-- Settings: the once-per-project chores -->
    <div v-else class="mt-5 grid max-w-4xl gap-6 md:grid-cols-2">
      <TeamPanel :project-id="projectId" />
      <MemoryPanel :project-id="projectId" :can-approve="canApproveMemory" />
      <GuidelinePanel :project-id="projectId" :can-edit="canEditGuideline" class="md:col-span-2" />
    </div>

    <!-- Delete: a real decision, stated in full -->
    <div
      v-if="deleting"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      @click.self="deleting = null"
    >
      <div class="w-full max-w-sm rounded-xl border border-edge-strong bg-panel-2 p-5">
        <h3 class="text-sm font-medium">Delete {{ deleting.entry.image.filename }}?</h3>
        <p class="mt-2 text-xs leading-relaxed text-neutral-400">
          This permanently removes the image and its full review history:
        </p>
        <ul v-if="deleting.preview" class="mt-2 space-y-1 text-xs text-neutral-300">
          <li>{{ deleting.preview.versions }} version{{ deleting.preview.versions > 1 ? 's' : '' }}</li>
          <li>{{ deleting.preview.defects }} defect{{ deleting.preview.defects === 1 ? '' : 's' }}, {{ deleting.preview.comments }} comment{{ deleting.preview.comments === 1 ? '' : 's' }}</li>
          <li v-if="deleting.preview.threads">{{ deleting.preview.threads }} review thread{{ deleting.preview.threads > 1 ? 's' : '' }}</li>
          <li>{{ deleting.preview.dismissals }} rejected finding{{ deleting.preview.dismissals === 1 ? '' : 's' }} (audit log)</li>
        </ul>
        <p v-else class="mt-2 text-xs text-neutral-500">Counting what this would remove…</p>
        <p class="mt-3 rounded bg-warning/10 px-2.5 py-1.5 text-[11px] text-warning">
          This can't be undone.
        </p>
        <p v-if="deleteError" class="mt-2 text-xs text-blocker">{{ deleteError }}</p>
        <div class="mt-4 flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-edge-strong px-3 py-1.5 text-xs text-neutral-300 hover:bg-edge"
            @click="deleting = null"
          >
            Cancel
          </button>
          <button
            type="button"
            :disabled="deleteBusy || !deleting.preview"
            class="rounded-md bg-red-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
            @click="confirmDelete"
          >
            {{ deleteBusy ? 'Deleting…' : 'Delete image' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
