<script>
import { archiveNote, liveVariants, slotPill, TONE_HEX, tipOf, versionTone } from '@/domain/slots'
import { shortDate } from '@/domain/time'

export default {
  name: 'SlotCard',
  props: {
    projectId: { type: String, required: true },
    slot: { type: Object, required: true },
    canUpload: { type: Boolean, default: false },
    canDelete: { type: Boolean, default: false },
  },
  emits: ['add-variant', 'delete', 'rename'],
  data() {
    return { showTree: false, menuOpen: false }
  },
  computed: {
    pill() {
      return slotPill(this.slot)
    },
    /** The variant the card represents: the winner if there is one, else the first live one. */
    lead() {
      const winner = this.slot.variants.find((variant) => variant.approved)
      return winner || liveVariants(this.slot)[0] || this.slot.variants[0]
    },
    cover() {
      return tipOf(this.lead)
    },
    hasVariants() {
      return this.slot.variants.length > 1
    },
    hasHistory() {
      return this.hasVariants || this.slot.variants.some((variant) => variant.versions.length > 1)
    },
  },
  methods: {
    archiveNote,
    shortDate,
    tipOf,
    toneHex(tone) {
      return TONE_HEX[tone]
    },
    /** The verdict dot for one node of the tree. */
    nodeTone(variant, version) {
      return versionTone(version, {
        approved: variant.approved && version.image.approved_by !== null,
      })
    },
    onVariantFile(fileList) {
      const file = Array.from(fileList).find((entry) => entry.type.startsWith('image/'))
      if (file) this.$emit('add-variant', { slotId: this.slot.slot_id, file })
      this.menuOpen = false
    },
  },
}
</script>

<template>
  <div
    class="group relative overflow-hidden rounded-lg border border-edge bg-panel transition hover:border-edge-strong"
    @mouseleave="menuOpen = false"
  >
    <RouterLink
      :to="{ name: 'review', params: { projectId, imageId: cover.image.id } }"
      class="block"
    >
      <img
        :src="cover.original_url"
        :alt="slot.name"
        class="aspect-square w-full object-cover"
      />
      <div class="flex items-center gap-2 px-3 py-2.5">
        <span class="min-w-0 truncate text-sm text-neutral-200">{{ slot.name }}</span>
        <span
          v-if="hasVariants"
          class="shrink-0 rounded-full border border-edge-strong px-1.5 text-[10px] text-neutral-500"
        >
          {{ slot.variants.length }} variants
        </span>
        <span class="ml-auto flex shrink-0 items-center gap-1.5 text-[11px] text-neutral-400">
          <span
            class="size-1.5 rounded-full"
            :class="pill.tone === 'busy' ? 'animate-pulse' : ''"
            :style="{ background: pill.dot }"
          />
          {{ pill.label }}
        </span>
      </div>
    </RouterLink>

    <!-- History: variants across, versions down. Never a diagonal — across is
         alternatives, down is time. -->
    <div v-if="hasHistory" class="border-t border-edge px-3 py-2">
      <button
        type="button"
        class="text-[11px] text-neutral-500 hover:text-neutral-300"
        @click="showTree = !showTree"
      >
        {{ showTree ? 'Hide history' : 'History' }}
      </button>

      <div v-if="showTree" class="mt-2 flex gap-2 overflow-x-auto pb-1">
        <div
          v-for="variant in slot.variants"
          :key="variant.variant"
          class="min-w-[8.5rem] shrink-0 rounded border border-edge p-1.5"
          :class="variant.archived_by !== null ? 'opacity-55' : ''"
        >
          <div class="flex items-baseline gap-1">
            <span class="text-[10px] font-medium text-neutral-400">
              Variant {{ variant.variant }}
            </span>
            <span
              v-if="variant.archived_by !== null"
              class="cursor-help text-[10px] text-neutral-600"
              :title="archiveNote(variant)"
            >
              archived
            </span>
            <span v-else-if="variant.approved" class="text-[10px] text-teal-300">winner</span>
          </div>

          <RouterLink
            v-for="version in variant.versions"
            :key="version.image.id"
            :to="{ name: 'review', params: { projectId, imageId: version.image.id } }"
            class="mt-1 block rounded px-1.5 py-1 hover:bg-edge"
          >
            <div class="flex items-center gap-1.5">
              <span
                class="size-1.5 shrink-0 rounded-full"
                :style="{ background: toneHex(nodeTone(variant, version)) }"
              />
              <span class="font-mono text-[11px] text-neutral-300">v{{ version.image.version }}</span>
              <span class="truncate text-[10px] text-neutral-500">
                {{ version.uploader_name || 'unknown' }}
              </span>
            </div>
            <div class="pl-3 text-[10px] text-neutral-600">
              {{ shortDate(version.image.created_at) }}
              <template v-if="version.open_defects">
                · {{ version.open_defects }} open
              </template>
            </div>
          </RouterLink>

          <!-- The audit answer reviewers actually ask for: who signed this off. -->
          <div
            v-if="variant.approved"
            class="mt-1 rounded bg-teal-300/10 px-1.5 py-1 text-[10px] text-teal-200"
          >
            Approved by {{ variant.approved_by_name || 'the owner' }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="canUpload || canDelete" class="absolute right-2 top-2">
      <button
        type="button"
        class="rounded-md bg-ink/80 px-2 py-0.5 text-sm text-neutral-300 opacity-0 backdrop-blur transition focus:opacity-100 group-hover:opacity-100 hover:text-white"
        aria-label="Slot actions"
        @click.stop.prevent="menuOpen = !menuOpen"
      >
        ⋯
      </button>
      <div
        v-if="menuOpen"
        class="absolute right-0 mt-1 w-44 overflow-hidden rounded-md border border-edge-strong bg-panel-2 py-1 text-sm shadow-xl"
      >
        <RouterLink
          :to="{ name: 'review', params: { projectId, imageId: cover.image.id } }"
          class="block px-3 py-1.5 text-neutral-300 hover:bg-edge hover:text-white"
        >
          Open review
        </RouterLink>
        <label
          v-if="canUpload"
          class="block cursor-pointer px-3 py-1.5 text-neutral-300 hover:bg-edge hover:text-white"
        >
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="hidden"
            @change="onVariantFile($event.target.files)"
          />
          Add variant…
        </label>
        <button
          v-if="canUpload"
          type="button"
          class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-edge hover:text-white"
          @click.stop.prevent="$emit('rename', slot); menuOpen = false"
        >
          Rename slot…
        </button>
        <button
          v-if="canDelete"
          type="button"
          class="block w-full px-3 py-1.5 text-left text-blocker hover:bg-edge"
          @click.stop.prevent="$emit('delete', slot); menuOpen = false"
        >
          Delete slot…
        </button>
      </div>
    </div>
  </div>
</template>
