import { defineStore } from 'pinia'

import api from '@/api'

// Pinia options syntax — AGENTS.md forbids setup stores.
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    resolved: false, // whether fetchMe has completed at least once
    loading: false,
  }),

  getters: {
    isAuthenticated: (state) => state.user !== null,
    displayName: (state) => state.user?.name || state.user?.email || '',
  },

  actions: {
    async fetchMe() {
      this.loading = true
      try {
        this.user = await api.get('/auth/me')
      } catch {
        this.user = null
      } finally {
        this.resolved = true
        this.loading = false
      }
    },

    login() {
      window.location.href = '/auth/login'
    },

    async logout() {
      await api.post('/auth/logout')
      this.user = null
    },
  },
})
