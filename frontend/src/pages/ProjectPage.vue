<script>
import { mapActions, mapState } from 'pinia'

import ActivityFeed from '@/components/ActivityFeed.vue'
import GuidelinePanel from '@/components/GuidelinePanel.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'
import SlotCard from '@/components/SlotCard.vue'
import TeamPanel from '@/components/TeamPanel.vue'
import UploadStaging from '@/components/UploadStaging.vue'
import { tipOf } from '@/domain/slots'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'
import { useSlotsStore } from '@/stores/slots'

export default {
  name: 'ProjectPage',
  components: {
    ActivityFeed,
    GuidelinePanel,
    MemoryPanel,
    SlotCard,
    TeamPanel,
    UploadStaging,
  },
  props: { projectId: { type: String, required: true } },
  data() {
    return {
      tab: 'assets',
      dragging: false,
      staged: [], // files waiting on the grouping decision
      deleting: null, // { slot, preview } while the modal is open
      deleteBusy: false,
      deleteError: '',
      renaming: null,
      renameValue: '',
    }
  },
  computed: {
    ...mapState(useProjectsStore, ['currentProject', 'currentRole']),
    ...mapState(useReviewStore, ['recentActivity', 'streaming']),
    ...mapState(useSlotsStore, ['slots', 'uploading', 'error', 'needsAttention', 'running']),
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
    lastActivityLine() {
      const last = this.recentActivity[0]
      return last ? `${last.stage.replaceAll('_', ' ')}${last.detail ? ` — ${last.detail}` : ''}` : ''
    },
  },
  watch: {
    /** The agent finishing changes what the cards say, so resync the slot list. */
    recentActivity(feed) {
      const latest = feed[0]
      if (latest && ['image_finished', 'image_failed', 'run_finished'].includes(latest.stage)) {
        this.fetchSlots(this.projectId)
      }
    },
  },
  async created() {
    await useProjectsStore().fetchOne(this.projectId)
    await this.fetchSlots(this.projectId)
    this.startStream(this.projectId)
  },
  beforeUnmount() {
    this.stopStream()
  },
  methods: {
    ...mapActions(useReviewStore, ['startStream', 'stopStream']),
    ...mapActions(useSlotsStore, ['fetchSlots', 'upload', 'addVariant', 'rename']),

    /** Picking files opens the staging strip; nothing uploads until it is confirmed. */
    onFiles(fileList) {
      const files = Array.from(fileList).filter((file) => file.type.startsWith('image/'))
      if (files.length) this.staged = files
    },

    onDrop(event) {
      this.dragging = false
      this.onFiles(event.dataTransfer.files)
    },

    async confirmUpload({ grouped }) {
      const files = this.staged
      this.staged = []
      const run = await this.upload(this.projectId, files, { grouped })
      // Straight into review — the agent works alongside, not in front of, the user.
      const first = run?.image_ids?.[0]
      if (first) {
        this.$router.push({ name: 'review', params: { projectId: this.projectId, imageId: first } })
      }
    },

    async onAddVariant({ slotId, file }) {
      const created = await this.addVariant(this.projectId, slotId, file)
      if (created?.id) {
        this.$router.push({
          name: 'review',
          params: { projectId: this.projectId, imageId: created.id },
        })
      }
    },

    /** Opening the modal fetches what would actually be destroyed. */
    async askDelete(slot) {
      this.deleteError = ''
      this.deleting = { slot, preview: null }
      try {
        this.deleting.preview = await useSlotsStore().deletePreview(this.projectId, slot.slot_id)
      } catch (error) {
        this.deleteError = error.message
      }
    },

    async confirmDelete() {
      if (!this.deleting) return
      this.deleteBusy = true
      this.deleteError = ''
      try {
        await useSlotsStore().deleteSlot(this.projectId, this.deleting.slot.slot_id)
        this.deleting = null
      } catch (error) {
        this.deleteError = error.message
      } finally {
        this.deleteBusy = false
      }
    },

    askRename(slot) {
      this.renaming = slot
      this.renameValue = slot.name
    },

    async confirmRename() {
      if (!this.renameValue.trim()) return
      await this.rename(this.projectId, this.renaming.slot_id, this.renameValue.trim())
      this.renaming = null
    },

    coverOf(slot) {
      return tipOf(slot.variants[0])
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
        {{ needsAttention }} slot{{ needsAttention > 1 ? 's' : '' }} need{{ needsAttention > 1 ? '' : 's' }} review
      </span>

      <label
        v-if="canUpload && tab === 'assets' && slots.length"
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
          { id: 'assets', label: `Slots ${slots.length || ''}` },
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
      <UploadStaging
        v-if="staged.length"
        :files="staged"
        :busy="uploading"
        class="mb-4"
        @confirm="confirmUpload"
        @cancel="staged = []"
      />

      <div
        v-if="running"
        class="mb-4 flex items-center gap-2.5 rounded-md border border-edge px-3 py-2"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-teal-300" />
        <span class="text-xs text-neutral-400">
          Agent working on {{ running }} slot{{ running > 1 ? 's' : '' }}
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
        v-if="canUpload && !slots.length && !staged.length"
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
        v-if="slots.length"
        class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        :class="dragging ? 'opacity-50' : ''"
      >
        <SlotCard
          v-for="slot in slots"
          :key="slot.slot_id"
          :project-id="projectId"
          :slot="slot"
          :can-upload="canUpload"
          :can-delete="canDelete"
          @add-variant="onAddVariant"
          @rename="askRename"
          @delete="askDelete"
        />
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
        <h3 class="text-sm font-medium">Delete {{ deleting.slot.name }}?</h3>
        <p class="mt-2 text-xs leading-relaxed text-neutral-400">
          This permanently removes every variant of this slot and its full review history:
        </p>
        <ul v-if="deleting.preview" class="mt-2 space-y-1 text-xs text-neutral-300">
          <li>{{ deleting.preview.variants }} variant{{ deleting.preview.variants > 1 ? 's' : '' }}, {{ deleting.preview.versions }} version{{ deleting.preview.versions > 1 ? 's' : '' }}</li>
          <li>{{ deleting.preview.defects }} defect{{ deleting.preview.defects === 1 ? '' : 's' }}, {{ deleting.preview.comments }} comment{{ deleting.preview.comments === 1 ? '' : 's' }}</li>
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
            {{ deleteBusy ? 'Deleting…' : 'Delete slot' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Rename: the slot is a creative intent, so let people say what it is -->
    <div
      v-if="renaming"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      @click.self="renaming = null"
    >
      <div class="w-full max-w-sm rounded-xl border border-edge-strong bg-panel-2 p-5">
        <h3 class="text-sm font-medium">Name this slot</h3>
        <p class="mt-1 text-xs text-neutral-500">
          What the variants are competing to be — "hero banner", not a filename.
        </p>
        <input
          v-model="renameValue"
          type="text"
          class="mt-3 w-full rounded-md border border-edge-strong bg-panel px-2.5 py-1.5 text-sm text-neutral-100 outline-none focus:border-neutral-500"
          @keyup.enter="confirmRename"
        />
        <div class="mt-4 flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-edge-strong px-3 py-1.5 text-xs text-neutral-300 hover:bg-edge"
            @click="renaming = null"
          >
            Cancel
          </button>
          <button
            type="button"
            :disabled="!renameValue.trim()"
            class="rounded-md bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-white disabled:opacity-50"
            @click="confirmRename"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
