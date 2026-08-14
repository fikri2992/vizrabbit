<script>
import { mapActions } from 'pinia'

import { useAuthStore } from '@/stores/auth'

export default {
  name: 'LoginPage',
  methods: {
    ...mapActions(useAuthStore, ['login']),
  },
}
</script>

<template>
  <div class="flex h-full flex-col items-center justify-center gap-8 px-6">
    <div class="max-w-md text-center">
      <h1 class="text-3xl font-semibold tracking-tight">Visual QA</h1>
      <p class="mt-3 text-neutral-400">
        Catch anatomy, physics, artifact and brand defects in AI-generated assets before they
        publish.
      </p>
    </div>

    <button
      class="rounded-lg bg-neutral-100 px-5 py-2.5 font-medium text-neutral-900 hover:bg-white"
      @click="login"
    >
      Continue with Google
    </button>
  </div>
</template>
