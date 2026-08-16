<script>
import { mapActions, mapState } from 'pinia'

import { useProjectsStore } from '@/stores/projects'

export default {
  name: 'DashboardPage',
  data() {
    return {
      name: '',
      creating: false,
      menuId: '',
      renaming: null, // { id, value } while the rename modal is open
      renameBusy: false,
      deleting: null, // { entry, preview } while the delete modal is open
      deleteBusy: false,
      modalError: '',
    }
  },
  computed: {
    ...mapState(useProjectsStore, ['items', 'loading', 'error']),
  },
  created() {
    this.fetchAll()
  },
  methods: {
    ...mapActions(useProjectsStore, [
      'fetchAll',
      'create',
      'rename',
      'remove',
      'deletePreview',
    ]),

    may(entry, permission) {
      return (entry.permissions || []).includes(permission)
    },

    async submit() {
      if (!this.name.trim()) return
      this.creating = true
      try {
        const project = await this.create(this.name.trim())
        this.name = ''
        this.$router.push({ name: 'project', params: { projectId: project.id } })
      } finally {
        this.creating = false
      }
    },

    askRename(entry) {
      this.menuId = ''
      this.modalError = ''
      this.renaming = { id: entry.project.id, value: entry.project.name }
    },

    async confirmRename() {
      if (!this.renaming?.value.trim()) return
      this.renameBusy = true
      this.modalError = ''
      try {
        await this.rename(this.renaming.id, this.renaming.value.trim())
        this.renaming = null
      } catch (error) {
        this.modalError = error.message
      } finally {
        this.renameBusy = false
      }
    },

    /** Opening the modal fetches what would actually be destroyed. */
    async askDelete(entry) {
      this.menuId = ''
      this.modalError = ''
      this.deleting = { entry, preview: null }
      try {
        this.deleting.preview = await this.deletePreview(entry.project.id)
      } catch (error) {
        this.modalError = error.message
      }
    },

    async confirmDelete() {
      if (!this.deleting) return
      this.deleteBusy = true
      this.modalError = ''
      try {
        await this.remove(this.deleting.entry.project.id)
        this.deleting = null
      } catch (error) {
        this.modalError = error.message
      } finally {
        this.deleteBusy = false
      }
    },

    /** Only the lines worth reading — a row of zeroes tells the owner nothing. */
    consequences(preview) {
      if (!preview) return []
      const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`
      return [
        preview.slots && plural(preview.slots, 'slot', 'slots'),
        preview.images && plural(preview.images, 'image', 'images'),
        preview.defects && plural(preview.defects, 'defect', 'defects'),
        preview.threads && plural(preview.threads, 'review thread', 'review threads'),
        preview.comments && plural(preview.comments, 'comment', 'comments'),
        preview.dismissals &&
          `${plural(preview.dismissals, 'rejected finding', 'rejected findings')} (audit log)`,
        preview.guidelines && plural(preview.guidelines, 'guideline', 'guidelines'),
        preview.memory_rules && plural(preview.memory_rules, 'memory rule', 'memory rules'),
      ].filter(Boolean)
    },
  },
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-6 py-10">
    <h2 class="text-xl font-medium tracking-tight">Projects</h2>

    <form class="mt-5 flex gap-2" @submit.prevent="submit">
      <input
        v-model="name"
        placeholder="New project name"
        class="flex-1 rounded-md border border-edge-strong bg-panel px-3 py-2 text-sm outline-none focus:border-neutral-500"
      />
      <button
        type="submit"
        :disabled="!name.trim() || creating"
        class="rounded-md bg-neutral-50 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:opacity-40"
      >
        Create
      </button>
    </form>
    <p class="mt-2 text-xs text-neutral-500">You become the brand owner of projects you create.</p>

    <p v-if="error" class="mt-4 text-sm text-blocker">{{ error }}</p>
    <p v-if="loading" class="mt-6 text-sm text-neutral-500">Loading…</p>

    <ul v-else-if="items.length" class="mt-6 divide-y divide-edge rounded-lg border border-edge bg-panel">
      <li
        v-for="entry in items"
        :key="entry.project.id"
        class="group relative"
        @mouseleave="menuId = ''"
      >
        <RouterLink
          :to="{ name: 'project', params: { projectId: entry.project.id } }"
          class="flex items-center justify-between px-4 py-3 hover:bg-panel-2"
        >
          <span class="font-medium">{{ entry.project.name }}</span>
          <span class="flex items-center gap-3 text-xs text-neutral-500">
            {{ entry.role }} · {{ entry.project.members.length }} member(s)
            <span
              v-if="may(entry, 'rename_project') || may(entry, 'delete_project')"
              class="w-4"
            />
          </span>
        </RouterLink>

        <div
          v-if="may(entry, 'rename_project') || may(entry, 'delete_project')"
          class="absolute right-2 top-1/2 -translate-y-1/2"
        >
          <button
            type="button"
            class="rounded-md px-2 py-0.5 text-sm text-neutral-400 opacity-0 transition focus:opacity-100 group-hover:opacity-100 hover:bg-edge hover:text-white"
            aria-label="Project actions"
            @click.stop.prevent="menuId = menuId === entry.project.id ? '' : entry.project.id"
          >
            ⋯
          </button>
          <div
            v-if="menuId === entry.project.id"
            class="absolute right-0 z-10 mt-1 w-44 overflow-hidden rounded-md border border-edge-strong bg-panel-2 py-1 text-sm shadow-xl"
          >
            <button
              v-if="may(entry, 'rename_project')"
              type="button"
              class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-edge hover:text-white"
              @click.stop.prevent="askRename(entry)"
            >
              Rename…
            </button>
            <button
              v-if="may(entry, 'delete_project')"
              type="button"
              class="block w-full px-3 py-1.5 text-left text-blocker hover:bg-edge"
              @click.stop.prevent="askDelete(entry)"
            >
              Delete project…
            </button>
          </div>
        </div>
      </li>
    </ul>

    <p v-else class="mt-8 text-sm text-neutral-500">
      No projects yet. Create one to start reviewing assets.
    </p>

    <!-- Rename -->
    <div
      v-if="renaming"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      @click.self="renaming = null"
    >
      <div class="w-full max-w-sm rounded-xl border border-edge-strong bg-panel-2 p-5">
        <h3 class="text-sm font-medium">Rename project</h3>
        <input
          v-model="renaming.value"
          type="text"
          maxlength="120"
          class="mt-3 w-full rounded-md border border-edge-strong bg-panel px-2.5 py-1.5 text-sm text-neutral-100 outline-none focus:border-neutral-500"
          @keyup.enter="confirmRename"
        />
        <p v-if="modalError" class="mt-2 text-xs text-blocker">{{ modalError }}</p>
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
            :disabled="!renaming.value.trim() || renameBusy"
            class="rounded-md bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-white disabled:opacity-50"
            @click="confirmRename"
          >
            {{ renameBusy ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete: the largest irreversible action in the app, stated in full -->
    <div
      v-if="deleting"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      @click.self="deleting = null"
    >
      <div class="w-full max-w-sm rounded-xl border border-edge-strong bg-panel-2 p-5">
        <h3 class="text-sm font-medium">Delete {{ deleting.entry.project.name }}?</h3>
        <p class="mt-2 text-xs leading-relaxed text-neutral-400">
          This permanently removes the project and everything in it:
        </p>
        <ul
          v-if="deleting.preview && consequences(deleting.preview).length"
          class="mt-2 space-y-1 text-xs text-neutral-300"
        >
          <li v-for="line in consequences(deleting.preview)" :key="line">{{ line }}</li>
        </ul>
        <p v-else-if="deleting.preview" class="mt-2 text-xs text-neutral-500">
          The project is empty — nothing has been uploaded to it yet.
        </p>
        <p v-else class="mt-2 text-xs text-neutral-500">Counting what this would remove…</p>
        <p
          v-if="deleting.preview && deleting.preview.members > 1"
          class="mt-2 text-xs text-neutral-400"
        >
          {{ deleting.preview.members - 1 }} other member(s) lose access.
        </p>
        <p class="mt-3 rounded bg-warning/10 px-2.5 py-1.5 text-[11px] text-warning">
          This can't be undone.
        </p>
        <p v-if="modalError" class="mt-2 text-xs text-blocker">{{ modalError }}</p>
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
            {{ deleteBusy ? 'Deleting…' : 'Delete project' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
