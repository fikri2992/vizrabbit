import { defineStore } from 'pinia'

import api from '@/api'
import { sortDefects, summarize } from '@/domain/defects'

const MAX_FEED_ITEMS = 200

export const useReviewStore = defineStore('review', {
  state: () => ({
    images: [], // [{ image, defects, original_url, annotated_url, gridded_url }]
    activeImage: null,
    thread: null, // { defect, comments, available_transitions }
    feed: [], // live agent activity
    streaming: false,
    uploading: false,
    error: '',
    closeStream: null,
  }),

  getters: {
    activeDefects: (state) => sortDefects(state.activeImage?.defects || []),
    activeSummary: (state) => summarize(state.activeImage?.defects || []),
    /** Latest first, for the activity panel. */
    recentActivity: (state) => [...state.feed].reverse(),
  },

  actions: {
    async fetchImages(projectId, runId = null) {
      const query = runId ? `?run_id=${runId}` : ''
      this.images = await api.get(`/api/projects/${projectId}/images${query}`)
    },

    async fetchImage(projectId, imageId) {
      this.activeImage = await api.get(`/api/projects/${projectId}/images/${imageId}`)
    },

    async upload(projectId, files) {
      this.uploading = true
      this.error = ''
      try {
        const form = new FormData()
        for (const file of files) form.append('files', file)
        const response = await fetch(`/api/projects/${projectId}/runs`, {
          method: 'POST',
          credentials: 'include',
          body: form,
        })
        if (!response.ok) throw new Error(await response.text())
        return response.json()
      } catch (error) {
        this.error = error.message
        throw error
      } finally {
        this.uploading = false
      }
    },

    // --- live agent activity ---

    startStream(projectId) {
      this.stopStream()
      this.closeStream = api.stream(`/api/projects/${projectId}/events`, {
        onOpen: () => {
          this.streaming = true
          // A reconnect may have missed events, so resync what they would have changed.
          this.fetchImages(projectId)
        },
        onEvent: (event) => this.pushEvent(projectId, event),
        onReconnecting: () => {
          this.streaming = false
        },
      })
    },

    stopStream() {
      if (this.closeStream) this.closeStream()
      this.closeStream = null
      this.streaming = false
    },

    pushEvent(projectId, event) {
      this.feed.push(event)
      if (this.feed.length > MAX_FEED_ITEMS) this.feed.shift()

      // An image finishing or failing changes what the dashboard should show.
      if (['image_finished', 'image_failed', 'run_finished'].includes(event.stage)) {
        this.fetchImages(projectId)
      }
    },

    clearFeed() {
      this.feed = []
    },

    // --- defect threads ---

    async openThread(projectId, defectId) {
      this.thread = await api.get(`/api/projects/${projectId}/defects/${defectId}`)
    },

    closeThread() {
      this.thread = null
    },

    async comment(projectId, defectId, body) {
      await api.post(`/api/projects/${projectId}/defects/${defectId}/comments`, { body })
      await this.openThread(projectId, defectId)
    },

    async transition(projectId, defectId, to, rationale = '') {
      const updated = await api.post(
        `/api/projects/${projectId}/defects/${defectId}/transition`,
        { to, rationale },
      )
      this.applyDefect(updated)
      await this.openThread(projectId, defectId)
      return updated
    },

    async setSeverity(projectId, defectId, severity) {
      const updated = await api.post(
        `/api/projects/${projectId}/defects/${defectId}/severity`,
        { severity },
      )
      this.applyDefect(updated)
    },

    async proposeMemoryRule(projectId, defectId, description) {
      return api.post(`/api/projects/${projectId}/defects/${defectId}/memory`, { description })
    },

    /** Upload a fixed version. The agent decides what that actually resolved. */
    async submitFix(projectId, imageId, file) {
      this.uploading = true
      this.error = ''
      try {
        const form = new FormData()
        form.append('file', file)
        const response = await fetch(
          `/api/projects/${projectId}/images/${imageId}/versions`,
          { method: 'POST', credentials: 'include', body: form },
        )
        if (!response.ok) throw new Error(await response.text())
        return response.json()
      } catch (error) {
        this.error = error.message
        throw error
      } finally {
        this.uploading = false
      }
    },

    async fetchVersions(projectId, imageId) {
      return api.get(`/api/projects/${projectId}/images/${imageId}/versions`)
    },

    async approveImage(projectId, imageId) {
      const updated = await api.post(`/api/projects/${projectId}/images/${imageId}/approve`)
      if (this.activeImage?.image.id === imageId) this.activeImage.image = updated
      return updated
    },

    /** Keep the loaded image's defect list in step after a change. */
    applyDefect(updated) {
      if (!this.activeImage) return
      this.activeImage.defects = this.activeImage.defects.map((defect) =>
        defect.id === updated.id ? updated : defect,
      )
    },
  },
})
