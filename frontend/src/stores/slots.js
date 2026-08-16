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
    /**
     * Load the work list. A failure here is reported, never thrown on:
     * this runs from the page's `created`, and an escaping rejection there
     * leaves the component half-mounted and the UI frozen with no message —
     * which looks exactly like a hung upload.
     */
    async fetchSlots(projectId) {
      this.loading = true
      this.error = ''
      try {
        this.slots = await api.get(`/api/projects/${projectId}/slots`)
      } catch (error) {
        this.error = error.message
        this.slots = []
      } finally {
        this.loading = false
      }
    },

    /**
     * Upload a batch. `grouped` collapses the whole batch into one slot's competing
     * variants; `slotId` appends them to a slot that already exists.
     */
    async upload(projectId, files, { grouped = false, slotId = '', placement = '' } = {}) {
      this.uploading = true
      this.error = ''
      try {
        const form = new FormData()
        for (const file of files) form.append('files', file)
        const group = groupingParam({ grouped, slotId })
        if (group) form.append('group_into', group)
        if (placement) form.append('placement', placement)

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

    /** Confirm the slot's definition of done — aspects like "16:9". */
    async setSpec(projectId, slotId, spec, dueAt = null) {
      await api.post(`/api/projects/${projectId}/slots/${slotId}/spec`, {
        spec,
        due_at: dueAt,
      })
      await this.fetchSlots(projectId)
    },

    /** Throw an agent draft away: defects reopen, the slot stops getting drafts. */
    async discardDraft(projectId, imageId) {
      await api.post(`/api/projects/${projectId}/images/${imageId}/discard_draft`)
      await this.fetchSlots(projectId)
    },

    /** Wave one mark away, for this user, permanently. */
    async dismissMark(projectId, key) {
      await api.post(`/api/projects/${projectId}/slots/marks/dismiss`, { key })
      // Cheap local removal — the server filters it on the next real fetch.
      this.slots = this.slots.map((slot) => ({
        ...slot,
        marks: (slot.marks || []).filter((mark) => mark.key !== key),
      }))
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
