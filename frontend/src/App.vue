<script>
import { mapActions, mapState } from 'pinia'

import NotificationBell from '@/components/NotificationBell.vue'
import { useAuthStore } from '@/stores/auth'

export default {
  name: 'App',
  components: { NotificationBell },
  computed: {
    ...mapState(useAuthStore, ['isAuthenticated', 'displayName']),
  },
  methods: {
    ...mapActions(useAuthStore, ['logout']),
    async signOut() {
      await this.logout()
      this.$router.push({ name: 'login' })
    },
  },
}
</script>

<template>
  <div class="flex min-h-full flex-col">
    <header
      v-if="isAuthenticated"
      class="flex items-center justify-between border-b border-neutral-800 px-6 py-3"
    >
      <RouterLink to="/" class="font-semibold tracking-tight">Visual QA</RouterLink>
      <div class="flex items-center gap-3 text-sm">
        <NotificationBell />
        <span class="text-neutral-400">{{ displayName }}</span>
        <button class="text-neutral-400 hover:text-neutral-100" @click="signOut">Sign out</button>
      </div>
    </header>

    <main class="flex-1">
      <RouterView />
    </main>
  </div>
</template>
