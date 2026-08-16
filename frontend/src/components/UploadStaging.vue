<script>
/**
 * The staging strip between picking files and starting the run.
 *
 * Grouping is offered here, never asked: the default is one slot per file, which
 * is exactly what upload did before slots existed, so the common path costs no
 * extra clicks and nobody has to learn the concept until they need it.
 */
export default {
  name: 'UploadStaging',
  props: {
    files: { type: Array, required: true },
    busy: { type: Boolean, default: false },
  },
  emits: ['confirm', 'cancel'],
  data() {
    return { grouped: false, placement: '', previews: [] }
  },
  computed: {
    summary() {
      if (this.files.length === 1) return '1 file · 1 slot'
      return this.grouped
        ? `${this.files.length} files · 1 slot, ${this.files.length} competing variants`
        : `${this.files.length} files · ${this.files.length} slots`
    },
  },
  created() {
    this.previews = this.files.map((file) => ({
      name: file.name,
      url: URL.createObjectURL(file),
    }))
  },
  beforeUnmount() {
    for (const preview of this.previews) URL.revokeObjectURL(preview.url)
  },
}
</script>

<template>
  <div class="rounded-lg border border-edge bg-panel p-3">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-medium text-neutral-200">Ready to upload</span>
      <span class="text-[11px] text-neutral-500">{{ summary }}</span>

      <div class="ml-auto flex items-center gap-2">
        <label
          v-if="files.length > 1"
          class="flex cursor-pointer items-center gap-1.5 text-[11px] text-neutral-400 hover:text-neutral-200"
        >
          <input v-model="grouped" type="checkbox" class="accent-neutral-300" />
          These are variants of one slot
        </label>
        <button
          type="button"
          class="rounded-md border border-edge-strong px-2.5 py-1 text-[11px] text-neutral-300 hover:bg-edge"
          @click="$emit('cancel')"
        >
          Cancel
        </button>
        <button
          type="button"
          :disabled="busy"
          class="rounded-md bg-neutral-50 px-3 py-1 text-[11px] font-medium text-neutral-900 hover:bg-white disabled:opacity-50"
          @click="$emit('confirm', { grouped, placement })"
        >
          {{ busy ? 'Uploading…' : 'Start review' }}
        </button>
      </div>
    </div>

    <!-- Intake question (decision 22): offered, never required — like grouping. -->
    <div class="mt-2 flex flex-wrap items-center gap-1.5 border-t border-edge pt-2">
      <span class="text-[11px] text-neutral-500">Where will these run?</span>
      <button
        v-for="where in ['tiktok', 'instagram', 'web']"
        :key="where"
        type="button"
        class="rounded-full px-2 py-0.5 text-[10px] capitalize transition"
        :class="
          placement === where
            ? 'bg-neutral-50 font-medium text-neutral-900'
            : 'border border-edge-strong text-neutral-400 hover:border-neutral-500 hover:text-neutral-200'
        "
        @click="placement = placement === where ? '' : where"
      >
        {{ where }}
      </button>
      <span class="text-[10px] text-neutral-600">
        {{ placement === 'tiktok' ? 'safe-area checks will watch the caption zone' : 'optional — it scopes the platform checks' }}
      </span>
    </div>

    <div class="mt-2.5 flex gap-2 overflow-x-auto pb-1">
      <div
        v-for="(preview, index) in previews"
        :key="preview.name + index"
        class="w-20 shrink-0"
      >
        <img
          :src="preview.url"
          :alt="preview.name"
          class="h-16 w-20 rounded border border-edge object-cover"
          :class="grouped ? 'border-teal-300/60' : ''"
        />
        <p class="mt-0.5 truncate text-[10px] text-neutral-500" :title="preview.name">
          {{ grouped ? `Variant ${index + 1}` : preview.name }}
        </p>
      </div>
    </div>
  </div>
</template>
