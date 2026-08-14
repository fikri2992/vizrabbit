<script>
import api from '@/api'

// Notifications are per-user, while the SSE stream is per-project, so this polls.
// Mentions are the whole point of the collaboration story; without somewhere to
// see them, being @-mentioned does nothing observable.
const POLL_MS = 30000

const KIND_LABEL = {
  mention: 'Mentioned you',
  run_finished: 'Run finished',
  memory_proposed: 'Memory rule proposed',
  defect_resolved: 'Defect verified fixed',
}

export default {
  name: 'NotificationBell',
  data() {
    return { items: [], open: false, timer: null }
  },
  computed: {
    count() {
      return this.items.length
    },
  },
  mounted() {
    this.load()
    this.timer = setInterval(this.load, POLL_MS)
    document.addEventListener('click', this.onDocumentClick)
  },
  beforeUnmount() {
    clearInterval(this.timer)
    document.removeEventListener('click', this.onDocumentClick)
  },
  methods: {
    async load() {
      try {
        this.items = await api.get('/api/notifications')
      } catch {
        // Signed out or offline; the next poll will recover.
      }
    },
    onDocumentClick(event) {
      if (!this.$el.contains(event.target)) this.open = false
    },
    async dismiss(notification) {
      await api.post(`/api/notifications/${notification.id}/read`)
      this.items = this.items.filter((item) => item.id !== notification.id)
    },
    async openItem(notification) {
      const link = notification.link
      await this.dismiss(notification)
      this.open = false
      if (link) this.$router.push(link)
    },
    label(notification) {
      return KIND_LABEL[notification.kind] || notification.kind
    },
    when(value) {
      return new Date(value).toLocaleString()
    },
  },
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="relative flex items-center gap-1.5 rounded px-2 py-1 text-sm text-neutral-400 hover:text-neutral-100"
      :aria-label="count ? `${count} unread notifications` : 'Notifications'"
      @click="open = !open"
    >
      <svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.6">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" stroke-linecap="round" />
        <path d="M13.7 21a2 2 0 0 1-3.4 0" stroke-linecap="round" />
      </svg>
      <span
        v-if="count"
        class="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white"
      >
        {{ count > 9 ? '9+' : count }}
      </span>
    </button>

    <div
      v-if="open"
      class="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-lg border border-neutral-700 bg-neutral-900 shadow-xl"
    >
      <p class="border-b border-neutral-800 px-4 py-2 text-xs font-medium uppercase tracking-wide text-neutral-500">
        Notifications
      </p>

      <ul v-if="items.length" class="max-h-80 divide-y divide-neutral-800 overflow-y-auto">
        <li v-for="item in items" :key="item.id">
          <button
            type="button"
            class="block w-full px-4 py-2.5 text-left hover:bg-neutral-800"
            @click="openItem(item)"
          >
            <span class="text-xs font-medium text-neutral-400">{{ label(item) }}</span>
            <span class="mt-0.5 block text-sm">{{ item.body }}</span>
            <span class="mt-0.5 block text-xs text-neutral-500">{{ when(item.created_at) }}</span>
          </button>
        </li>
      </ul>

      <p v-else class="px-4 py-6 text-center text-sm text-neutral-500">Nothing new.</p>
    </div>
  </div>
</template>
