<script>
import { mapActions, mapState } from 'pinia'

import api from '@/api'
import { useProjectsStore } from '@/stores/projects'

// What each role can actually do, in the words of the people doing it. The role
// picker is where the accountability model becomes visible to a user, so it says
// what it means rather than just naming the role.
const ROLE_HELP = {
  owner: 'Answers guideline questions, approves memory rules, dismisses false positives, and approves assets. Exactly one per project.',
  reviewer: 'Uploads assets, submits fixes, comments, and proposes memory rules.',
  viewer: 'Reads and comments. Cannot change anything.',
}

export default {
  name: 'TeamPanel',
  props: {
    projectId: { type: String, required: true },
  },
  data() {
    return { email: '', role: 'reviewer', busy: false, error: '', roleHelp: ROLE_HELP }
  },
  computed: {
    ...mapState(useProjectsStore, ['currentProject']),
    members() {
      return this.currentProject?.members || []
    },
    canManage() {
      return useProjectsStore().can('manage_members')
    },
    pendingCount() {
      return this.members.filter((m) => m.user_id.startsWith('email:')).length
    },
  },
  methods: {
    ...mapActions(useProjectsStore, ['fetchOne']),
    async invite() {
      const email = this.email.trim()
      if (!email.includes('@')) return
      this.busy = true
      this.error = ''
      try {
        await useProjectsStore().invite(this.projectId, email, this.role)
        this.email = ''
      } catch (error) {
        this.error = error.message.includes('409')
          ? 'That person is already on the project.'
          : error.message
      } finally {
        this.busy = false
      }
    },
    async remove(member) {
      this.error = ''
      try {
        await api.del(`/api/projects/${this.projectId}/members/${member.user_id}`)
        await this.fetchOne(this.projectId)
      } catch (error) {
        this.error = error.message
      }
    },
    /** Invitees keep a placeholder id until their first sign-in. */
    isPending(member) {
      return member.user_id.startsWith('email:')
    },
    initials(member) {
      const source = member.name || member.email
      return source.slice(0, 2).toUpperCase()
    },
  },
}
</script>

<template>
  <section class="rounded-lg border border-neutral-800 bg-neutral-900/50">
    <header class="flex items-center gap-2 border-b border-neutral-800 px-4 py-2.5">
      <h3 class="text-sm font-medium">Team</h3>
      <span class="ml-auto text-xs text-neutral-500">{{ members.length }}</span>
    </header>

    <div class="space-y-4 p-4">
      <ul class="space-y-2">
        <li v-for="member in members" :key="member.user_id" class="flex items-center gap-3">
          <span
            class="flex size-8 shrink-0 items-center justify-center rounded-full bg-neutral-800 text-xs font-semibold text-neutral-300"
            aria-hidden="true"
          >
            {{ initials(member) }}
          </span>

          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm">{{ member.name || member.email }}</span>
            <span class="block truncate text-xs text-neutral-500">
              {{ member.email }}
              <template v-if="isPending(member)"> · not signed in yet</template>
            </span>
          </span>

          <span
            class="shrink-0 rounded-full px-2 py-0.5 text-xs ring-1 ring-inset"
            :class="
              member.role === 'owner'
                ? 'bg-neutral-100 text-neutral-900 ring-neutral-100'
                : 'text-neutral-400 ring-neutral-700'
            "
          >
            {{ member.role }}
          </span>

          <button
            v-if="canManage && member.role !== 'owner'"
            type="button"
            class="shrink-0 text-xs text-neutral-500 hover:text-red-400"
            :aria-label="`Remove ${member.email}`"
            @click="remove(member)"
          >
            Remove
          </button>
        </li>
      </ul>

      <form v-if="canManage" class="space-y-2 border-t border-neutral-800 pt-4" @submit.prevent="invite">
        <div class="flex gap-2">
          <input
            v-model="email"
            type="email"
            placeholder="teammate@company.com"
            class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-neutral-500"
          />
          <select
            v-model="role"
            class="rounded border border-neutral-700 bg-neutral-900 px-2 py-2 text-sm"
          >
            <option value="reviewer">Reviewer</option>
            <option value="viewer">Viewer</option>
          </select>
          <button
            type="submit"
            :disabled="busy || !email.includes('@')"
            class="rounded bg-neutral-100 px-3 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
          >
            Invite
          </button>
        </div>

        <p class="text-xs text-neutral-500">{{ roleHelp[role] }}</p>
        <p v-if="error" class="text-xs text-red-400">{{ error }}</p>
      </form>

      <p v-else class="border-t border-neutral-800 pt-3 text-xs text-neutral-500">
        Only the brand owner can change who is on this project.
      </p>
    </div>
  </section>
</template>
