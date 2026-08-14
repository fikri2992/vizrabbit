import { defineStore } from 'pinia'

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
