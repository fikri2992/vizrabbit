<script>
import { mapActions, mapState } from 'pinia'

import { useProjectsStore } from '@/stores/projects'

export default {
  name: 'DashboardPage',
  data() {
    return { name: '', creating: false }
  },
  computed: {
    ...mapState(useProjectsStore, ['items', 'loading', 'error']),
  },
  created() {
    this.fetchAll()
  },
  methods: {
    ...mapActions(useProjectsStore, ['fetchAll', 'create']),
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
  },
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-6 py-10">
    <h2 class="text-xl font-semibold tracking-tight">Projects</h2>

    <form class="mt-5 flex gap-2" @submit.prevent="submit">
      <input
        v-model="name"
        placeholder="New project name"
        class="flex-1 rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-neutral-500"
      />
      <button
        type="submit"
        :disabled="!name.trim() || creating"
        class="rounded bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
      >
        Create
      </button>
    </form>
    <p class="mt-2 text-xs text-neutral-500">You become the brand owner of projects you create.</p>

    <p v-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>
    <p v-if="loading" class="mt-6 text-sm text-neutral-500">Loading…</p>

    <ul v-else-if="items.length" class="mt-6 divide-y divide-neutral-800 rounded-lg border border-neutral-800">
      <li v-for="entry in items" :key="entry.project.id">
        <RouterLink
          :to="{ name: 'project', params: { projectId: entry.project.id } }"
          class="flex items-center justify-between px-4 py-3 hover:bg-neutral-900"
        >
          <span class="font-medium">{{ entry.project.name }}</span>
          <span class="text-xs text-neutral-500">
            {{ entry.role }} · {{ entry.project.members.length }} member(s)
          </span>
        </RouterLink>
      </li>
    </ul>

    <p v-else class="mt-8 text-sm text-neutral-500">
      No projects yet. Create one to start reviewing assets.
    </p>
  </div>
</template>
