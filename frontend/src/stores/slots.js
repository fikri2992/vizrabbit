import { acceptHMRUpdate, defineStore } from 'pinia'

import api from '@/api'
import { groupingParam, liveVariants, openDefects } from '@/domain/slots'

export const useSlotsStore = defineStore('slots', {
  state: () => ({
    slots: [], // [{ slot_id, name, state, synthetic, variants: [...] }]
    loading: false,
    uploading: false,
    error: '',
  }),

  getters: {
    /** Slots still waiting on a human — complete ones and archived work excluded. */
    needsAttention: (state) =>
      state.slots.filter((slot) => slot.state !== 'complete' && openDefects(slot) > 0).length,

    running: (state) =>
      state.slots.filter((slot) =>
        liveVariants(slot).some((variant) =>
          variant.versions.some((version) =>
            ['queued', 'scanning', 'reviewing'].includes(version.image.status),
          ),
        ),
      ).length,

    slotById: (state) => (slotId) => state.slots.find((slot) => slot.slot_id === slotId) || null,
  },

  actions: {
    async fetchSlots(projectId) {
      this.loading = true
      try {
        this.slots = await api.get(`/api/projects/${projectId}/slots`)
      } finally {
        this.loading = false
      }
    },

    /**
     * Upload a batch. `grouped` collapses the whole batch into one slot's competing
     * variants; `slotId` appends them to a slot that already exists.
     */
    async upload(projectId, files, { grouped = false, slotId = '' } = {}) {
      this.uploading = true
      this.error = ''
      try {
        const form = new FormData()
        for (const file of files) form.append('files', file)
        const group = groupingParam({ grouped, slotId })
        if (group) form.append('group_into', group)

        const response = await fetch(`/api/projects/${projectId}/runs`, {
          method: 'POST',
          credentials: 'include',
          body: form,
        })
        if (!response.ok) throw new Error(await response.text())
        const run = await response.json()
        await this.fetchSlots(projectId)
        return run
      } catch (error) {
        this.error = error.message
        throw error
      } finally {
        this.uploading = false
      }
    },

    /** Add one competing candidate to an existing slot — the anti-fork escape hatch. */
    async addVariant(projectId, slotId, file) {
      this.uploading = true
      this.error = ''
      try {
        const form = new FormData()
        form.append('file', file)
        const response = await fetch(`/api/projects/${projectId}/slots/${slotId}/variants`, {
          method: 'POST',
          credentials: 'include',
          body: form,
        })
        if (!response.ok) throw new Error(await response.text())
        const created = await response.json()
        await this.fetchSlots(projectId)
        return created
      } catch (error) {
        this.error = error.message
        throw error
      } finally {
        this.uploading = false
      }
    },

    async rename(projectId, slotId, name) {
      await api.post(`/api/projects/${projectId}/slots/${slotId}/name`, { name })
      await this.fetchSlots(projectId)
    },

    async deletePreview(projectId, slotId) {
      return api.get(`/api/projects/${projectId}/slots/${slotId}/delete_preview`)
    },

    async deleteSlot(projectId, slotId) {
      await api.del(`/api/projects/${projectId}/slots/${slotId}`)
      await this.fetchSlots(projectId)
    },
  },
})

// Hot-swap actions during dev instead of stranding components on a stale store.
if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useSlotsStore, import.meta.hot))
}
