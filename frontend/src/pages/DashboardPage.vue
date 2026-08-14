<script>
import { mapState } from 'pinia'

import { useAuthStore } from '@/stores/auth'

export default {
  name: 'DashboardPage',
  computed: {
    ...mapState(useAuthStore, ['displayName']),
  },
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-6 py-10">
    <h2 class="text-xl font-semibold tracking-tight">Projects</h2>
    <p class="mt-2 text-sm text-neutral-400">
      Signed in as {{ displayName }}. Project list arrives in Phase 2.
    </p>
  </div>
</template>
