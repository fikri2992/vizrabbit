import { acceptHMRUpdate, defineStore } from 'pinia'

import api from '@/api'

export const useProjectsStore = defineStore('projects', {
  state: () => ({
    items: [], // [{ project, role, permissions }]
    current: null,
    loading: false,
    error: '',
  }),

  getters: {
    currentProject: (state) => state.current?.project || null,
    currentRole: (state) => state.current?.role || null,
    can: (state) => (permission) => (state.current?.permissions || []).includes(permission),
    isOwner: (state) => state.current?.role === 'owner',
  },

  actions: {
    async fetchAll() {
      this.loading = true
      this.error = ''
      try {
        this.items = await api.get('/api/projects')
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    },

    async fetchOne(projectId) {
      this.loading = true
      this.error = ''
      try {
        this.current = await api.get(`/api/projects/${projectId}`)
      } catch (error) {
        this.error = error.message
        this.current = null
      } finally {
        this.loading = false
      }
    },

    async create(name) {
      const created = await api.post('/api/projects', { name })
      this.items.unshift(created)
      return created.project
    },

    async rename(projectId, name) {
      const updated = await api.post(`/api/projects/${projectId}/name`, { name })
      const index = this.items.findIndex((entry) => entry.project.id === projectId)
      if (index !== -1) this.items.splice(index, 1, updated)
      if (this.current?.project.id === projectId) this.current = updated
      return updated.project
    },

    /** What deleting this project would destroy — shown before the owner confirms. */
    async deletePreview(projectId) {
      return api.get(`/api/projects/${projectId}/delete_preview`)
    },

    async remove(projectId) {
      const removed = await api.del(`/api/projects/${projectId}`)
      this.items = this.items.filter((entry) => entry.project.id !== projectId)
      if (this.current?.project.id === projectId) this.current = null
      return removed
    },

    async invite(projectId, email, role) {
      this.current = await api.post(`/api/projects/${projectId}/members`, { email, role })
    },

    async addGuideline(projectId, name, rawText) {
      return api.post(`/api/projects/${projectId}/guidelines`, { name, raw_text: rawText })
    },

    async fetchGuidelines(projectId) {
      return api.get(`/api/projects/${projectId}/guidelines`)
    },
  },
})

// Hot-swap actions during dev instead of stranding components on a stale store.
if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useProjectsStore, import.meta.hot))
}
