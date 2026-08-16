<script>
import { mapActions, mapState } from 'pinia'

import ActivityFeed from '@/components/ActivityFeed.vue'
import DefectThread from '@/components/DefectThread.vue'
import ReviewCanvas from '@/components/ReviewCanvas.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import VoicePanel from '@/components/VoicePanel.vue'
import { isClear, isQuestion, sortDefects } from '@/domain/defects'
import { slotCaption, variantNeighbours } from '@/domain/slots'
import { ago } from '@/domain/time'
import { useProjectsStore } from '@/stores/projects'
import { useReviewStore } from '@/stores/review'

const TOOLS = [
  { id: 'select', label: 'Select and pan', icon: 'M4 4l7 16 2.5-6.5L20 11z' },
  { id: 'circle', label: 'Circle', icon: '' },
  { id: 'rect', label: 'Rectangle', icon: '' },
  { id: 'arrow', label: 'Arrow', icon: '' },
  { id: 'path', label: 'Freehand', icon: '' },
]

const COLORS = ['#E24B4A', '#EF9F27', '#378ADD', '#22C55E', '#E879F9']

const SEVERITY_HEX = { blocker: '#E24B4A', warning: '#EF9F27', nitpick: '#378ADD' }

const AGENT_STATE_LABEL = {
  inspecting: 'agent inspecting…',
  answered: '',
  failed: 'inspection failed',
}

export default {
  name: 'ReviewPage',
  components: { ActivityFeed, DefectThread, ReviewCanvas, SeverityChip, VoicePanel },
  props: {
    projectId: { type: String, required: true },
    imageId: { type: String, required: true },
  },
  data() {
    return {
      selectedId: '',
      hoveredId: '',
      tab: 'comments',
      tool: 'select',
      color: COLORS[0],
      pendingShapes: [],
      composerBody: '',
      askAgent: false,
      posting: false,
      openOnly: false,
      notice: '',
      finishedNotice: '',
      versions: [],
      placement: null, // phase 9 advisories for the run's declared platform
      placementOverlay: false,
      voiceSession: null, // phase 14: an open Live session, or null
      voiceHidden: false, // a failed request hides the control silently
      shown: null, // { src, width, height } — swapped only once decoded, so
      // stepping between variants never flashes a half-loaded frame
      replyDrafts: {},
      tools: TOOLS,
      colors: COLORS,
    }
  },
  computed: {
    ...mapState(useReviewStore, [
      'activeImage',
      'thread',
      'activeSummary',
      'uploading',
      'dismissals',
      'threads',
      'recentActivity',
      'streaming',
    ]),
    defects() {
      return sortDefects(this.activeImage?.defects || [])
    },
    /** Defects and human threads as one rail, ordered by pin. */
    railItems() {
      const defectItems = this.defects.map((defect) => ({
        kind: 'defect',
        id: defect.id,
        pin: defect.pin,
        open: ['open', 'needs_human_review'].includes(defect.status),
        defect,
      }))
      const threadItems = this.threads.map(({ thread, comments }) => ({
        kind: 'thread',
        id: thread.id,
        pin: thread.pin,
        open: !thread.resolved,
        thread,
        comments,
      }))
      const merged = [...defectItems, ...threadItems].sort((a, b) => a.pin - b.pin)
      return this.openOnly ? merged.filter((item) => item.open) : merged
    },
    can() {
      return useProjectsStore().can
    },
    /** The agent has this image on its bench right now. */
    agentWorking() {
      return ['queued', 'scanning', 'reviewing'].includes(this.activeImage?.image.status)
    },
    /** The narrated feed, scoped to the image on screen. */
    imageActivity() {
      return this.recentActivity.filter(
        (event) => event.detail?.image_id === this.imageId,
      )
    },
    statusPill() {
      if (this.agentWorking) return { label: 'Agent reviewing…', tone: 'violet' }
      if (this.activeImage?.image.status === 'failed') return { label: 'Failed', tone: 'amber' }
      if (this.activeImage?.image.approved_by) return { label: 'Approved', tone: 'green' }
      const { open, inFlight } = this.activeSummary
      if (inFlight) return { label: 'Agent re-checking', tone: 'violet' }
      if (open) return { label: 'Needs review', tone: 'amber' }
      return { label: 'Clear', tone: 'green' }
    },
    everythingClosed() {
      return isClear(this.defects)
    },
    /** The agent's unanswered questions on this image — what voice talks through. */
    openQuestions() {
      return this.defects.filter((defect) => isQuestion(defect))
    },
    /** Video defects with a shot range — what the timeline draws. */
    timedDefects() {
      return this.defects.filter((defect) => typeof defect.time_start === 'number')
    },
    approved() {
      return Boolean(this.activeImage?.image.approved_by)
    },
    slotContext() {
      return this.activeImage?.slot || null
    },
    slotCaption() {
      return slotCaption(this.slotContext)
    },
    variantNeighbours() {
      return variantNeighbours(this.slotContext)
    },
    /** A superseded variant is still readable; it just is not the one that won. */
    archivedBy() {
      return this.slotContext?.archived_by ?? null
    },
  },
  watch: {
    imageId() {
      this.load()
    },
    activeImage: {
      immediate: true,
      handler() {
        this.syncShown()
      },
    },
    // The agent finished while the user was drawing or reading — tell them
    // quietly; the pins have already appeared via the store refetch.
    agentWorking(now, before) {
      if (before && !now) {
        if (this.activeImage?.image.status === 'failed') {
          this.finishedNotice = 'The agent could not finish this image — see Activity.'
          return
        }
        // The finished event carries the authoritative counts; local defect and
        // dismissal lists may still be refetching when this fires.
        const done = this.imageActivity.find((event) => event.stage === 'image_finished')
        const found = done?.detail?.defects ?? this.defects.length
        const rejected = done?.detail?.dismissed ?? this.dismissals.length
        this.finishedNotice =
          `Agent finished — ${found} finding${found === 1 ? '' : 's'}, ${rejected} rejected`
      }
    },
  },
  async created() {
    await this.load()
    window.addEventListener('keydown', this.onKey)
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.onKey)
  },
  methods: {
    ...mapActions(useReviewStore, [
      'fetchImage',
      'fetchThreads',
      'fetchDismissals',
      'fetchVersions',
      'openThread',
      'comment',
      'transition',
      'answerQuestion',
      'openVoiceSession',
      'proposeMemoryRule',
      'approveImage',
      'submitFix',
      'fetchPlacement',
      'decidePlacement',
      'createThread',
      'replyThread',
      'resolveThread',
      'startStream',
      'stopStream',
    ]),
    async load() {
      this.notice = ''
      this.finishedNotice = ''
      this.selectedId = ''
      this.pendingShapes = []
      this.voiceSession = null
      await useProjectsStore().fetchOne(this.projectId)
      await this.fetchImage(this.projectId, this.imageId)
      this.fetchThreads(this.projectId, this.imageId)
      this.fetchDismissals(this.projectId, this.imageId)
      this.versions = await this.fetchVersions(this.projectId, this.imageId)
      this.fetchPlacement(this.projectId, this.imageId)
        .then((view) => (this.placement = view.platform ? view : null))
        .catch(() => {})
      this.startStream(this.projectId)
      this.prefetchSiblings()
      // Fresh upload: open on the agent's live narration instead of an empty rail.
      if (this.agentWorking) this.tab = 'activity'
      const first = this.railItems[0]
      if (first) this.select(first)
    },

    /**
     * Swap what the canvas shows only after the next original has decoded:
     * the old frame stays up during the (cached, fast) decode, so a variant
     * switch is one clean replacement instead of a flash of blank.
     */
    async syncShown() {
      const view = this.activeImage
      if (!view || view.image.kind === 'video') return
      const src = view.original_url
      if (this.shown?.src === src) return
      const probe = new Image()
      probe.src = src
      // decode() gives the cleanest swap but can stall forever in a hidden
      // tab, and onload alone misses the decode. Race them, capped: whichever
      // fires first wins, and 400ms of waiting is worse than one soft flash.
      await new Promise((resolve) => {
        probe.onload = resolve
        probe.onerror = resolve
        probe.decode?.().then(resolve, resolve)
        setTimeout(resolve, 400)
      })
      if (this.activeImage?.original_url === src) {
        this.shown = { src, width: view.image.width, height: view.image.height }
      }
    },

    /**
     * Warm the browser cache with the sibling variants' originals, so stepping
     * V1→V2 swaps an already-decoded image instead of flashing while it loads.
     */
    prefetchSiblings() {
      const ids = new Set([
        ...(this.slotContext?.siblings || []).map((sibling) => sibling.image_id),
        ...this.versions.map((version) => version.id),
      ])
      ids.delete(this.imageId)
      for (const id of ids) {
        const image = new Image()
        image.src = `/api/blobs/projects/${this.projectId}/images/${id}/original.png`
      }
    },

    /**
     * Back means "where I came from" — the tree, the cards, compare — not a
     * hardcoded destination. Only a cold-opened tab (no in-app history) falls
     * back to the project page.
     */
    goBack() {
      if (window.history.state?.back) this.$router.back()
      else this.$router.push({ name: 'project', params: { projectId: this.projectId } })
    },

    async select(item) {
      this.selectedId = item.id
      if (item.kind === 'defect') await this.openThread(this.projectId, item.id)
    },

    onCanvasSelect(canvasItem) {
      const item = this.railItems.find((entry) => entry.id === canvasItem.id)
      if (item) {
        this.tab = 'comments'
        this.select(item)
      }
    },

    onKey(event) {
      const tag = event.target.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      const step = { j: 1, ArrowDown: 1, k: -1, ArrowUp: -1 }[event.key]
      if (step) {
        const list = this.railItems
        if (!list.length) return
        event.preventDefault()
        const current = list.findIndex((item) => item.id === this.selectedId)
        const next = current === -1 ? 0 : (current + step + list.length) % list.length
        this.select(list[next])
        return
      }
      // Comparing candidates is the reason variants exist, so give it a key.
      const sideways = { '[': 'previous', ']': 'next' }[event.key]
      if (sideways) {
        const target = this.variantNeighbours[sideways]
        if (target) {
          event.preventDefault()
          this.$router.push({
            name: 'review',
            params: { projectId: this.projectId, imageId: target.image_id },
          })
        }
        return
      }
      const tool = { v: 'select', c: 'circle', r: 'rect', a: 'arrow', p: 'path' }[event.key]
      if (tool && this.can('comment')) this.tool = tool
      if (event.key === 'Escape') {
        this.tool = 'select'
        this.pendingShapes = []
      }
    },

    onShape(shape) {
      this.pendingShapes.push(shape)
      // One deliberate shape per gesture; freehand stays armed for multi-stroke.
      if (this.tool !== 'path') this.tool = 'select'
      this.$refs.composer?.focus()
    },

    async postThread() {
      if (!this.composerBody.trim() || !this.pendingShapes.length) return
      this.posting = true
      this.notice = ''
      try {
        const created = await this.createThread(this.projectId, this.imageId, {
          body: this.composerBody,
          shapes: this.pendingShapes,
          askAgent: this.askAgent,
        })
        this.composerBody = ''
        this.pendingShapes = []
        this.askAgent = false
        this.tab = 'comments'
        this.selectedId = created.thread.id
      } catch (error) {
        this.notice = error.message
      } finally {
        this.posting = false
      }
    },

    async sendReply(item) {
      const body = (this.replyDrafts[item.id] || '').trim()
      if (!body) return
      await this.replyThread(this.projectId, item.id, body)
      this.replyDrafts[item.id] = ''
    },

    agentStateLabel(thread) {
      return AGENT_STATE_LABEL[thread.agent_state] ?? ''
    },

    async onComment(body) {
      await this.comment(this.projectId, this.selectedId, body)
    },
    async onTransition({ to, rationale }) {
      try {
        await this.transition(this.projectId, this.selectedId, to, rationale)
        this.notice = ''
      } catch (error) {
        this.notice = error.message
      }
    },
    timecode(seconds) {
      const s = Math.floor(seconds || 0)
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
    },
    seekTo(at, defectId) {
      const player = this.$refs.player
      if (player) player.currentTime = at
      if (defectId) this.selectedId = defectId
    },
    async onDecidePlacement(key, decision) {
      await this.decidePlacement(this.projectId, this.imageId, key, decision)
      this.placement = await this.fetchPlacement(this.projectId, this.imageId)
    },
    async onAnswer({ confirmed }) {
      try {
        const result = await this.answerQuestion(this.projectId, this.selectedId, confirmed)
        this.notice = result.adjustment || (confirmed ? 'Kept as a real defect.' : 'Dismissed.')
      } catch (error) {
        this.notice = error.message
      }
    },
    /** Phase 14: open a constrained Live session. Any refusal hides the control. */
    async startVoice() {
      try {
        this.voiceSession = await this.openVoiceSession(this.projectId, this.imageId)
      } catch {
        this.voiceHidden = true
      }
    },
    /** A spoken answer is the clicked one: the exact same store action. */
    async onVoiceAnswer({ defectId, confirmed }) {
      try {
        const result = await this.answerQuestion(this.projectId, defectId, confirmed)
        this.notice = result.adjustment || (confirmed ? 'Kept as a real defect.' : 'Dismissed.')
      } catch (error) {
        this.notice = error.message
      }
    },
    onVoiceNavigate(step) {
      const questions = this.railItems.filter(
        (item) => item.kind === 'defect' && isQuestion(item.defect),
      )
      if (!questions.length) return
      const current = questions.findIndex((item) => item.id === this.selectedId)
      const next = (current + step + questions.length) % questions.length
      this.select(questions[next])
    },
    async onProposeMemory(description) {
      const proposal = await this.proposeMemoryRule(this.projectId, this.selectedId, description)
      this.notice = proposal.collisions.length
        ? `Proposed — overlaps ${proposal.collisions.length} existing rule(s); the owner will reconcile.`
        : 'Proposed. The brand owner approves it before it takes effect.'
    },
    async onApprove() {
      try {
        await this.approveImage(this.projectId, this.imageId)
        await this.fetchImage(this.projectId, this.imageId)
        const siblings = (this.slotContext?.variant_count ?? 1) - 1
        this.notice = siblings
          ? `Approved. This slot is complete — ${siblings} other variant${siblings === 1 ? '' : 's'} archived.`
          : 'Approved.'
      } catch (error) {
        this.notice = error.message
      }
    },
    async onFixSelected(files) {
      const file = files?.[0]
      if (!file) return
      try {
        const result = await this.submitFix(this.projectId, this.imageId, file)
        const count = result.submitted.length
        this.notice = count
          ? `Version ${result.version.version} uploaded — the agent is re-checking ${count} defect(s).`
          : `Version ${result.version.version} uploaded. Nothing was open to re-check.`
        this.versions = await this.fetchVersions(this.projectId, this.imageId)
      } catch (error) {
        // A fork is not a failure, it is a different action: this version has
        // already been fixed once, so the competing attempt belongs in a variant.
        this.notice = error.message.includes('409')
          ? 'This version already has a fix. Add a competing variant from the slot card instead.'
          : error.message
      }
    },
    ago,

    /** The rail echoes the canvas: pins share one colour language. */
    pinColor(item) {
      if (item.kind === 'defect') return SEVERITY_HEX[item.defect.severity] || '#888'
      return item.thread.shapes[0]?.color || '#378ADD'
    },
  },
}
</script>

<template>
  <div v-if="activeImage" class="flex h-[calc(100vh-53px)] flex-col">
    <!-- Top bar -->
    <header class="flex items-center gap-3 border-b border-neutral-800 px-4 py-2">
      <button
        type="button"
        class="text-neutral-400 hover:text-neutral-100"
        aria-label="Back"
        @click="goBack"
      >
        <svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>

      <div class="min-w-0">
        <h2 class="truncate text-sm font-semibold">{{ activeImage.image.filename }}</h2>
        <p v-if="slotCaption" class="truncate text-[11px] text-neutral-500">
          {{ slotCaption }}
        </p>
      </div>

      <!-- Competing candidates sit side by side; stepping between them is the
           comparison affordance, so it lives next to the title. -->
      <div v-if="slotContext && slotContext.variant_count > 1" class="flex items-center gap-1">
        <RouterLink
          v-for="sibling in slotContext.siblings"
          :key="sibling.variant"
          :to="{ name: 'review', params: { projectId, imageId: sibling.image_id } }"
          class="rounded-full px-2 py-0.5 text-xs ring-1 ring-inset"
          :class="[
            sibling.variant === slotContext.variant
              ? 'bg-neutral-100 text-neutral-900 ring-neutral-100'
              : 'text-neutral-400 ring-neutral-700 hover:text-neutral-100',
            sibling.archived ? 'opacity-60' : '',
          ]"
          :title="sibling.approved ? 'Approved variant' : sibling.archived ? 'Superseded' : ''"
        >
          {{ sibling.approved ? '★ ' : '' }}V{{ sibling.variant }}
        </RouterLink>
        <!-- Seeing the difference beats remembering it (decision 25). -->
        <RouterLink
          :to="{
            name: 'slot-flow',
            params: { projectId, slotId: slotContext.slot_id },
            query: { compare: '1', left: imageId },
          }"
          class="ml-1 rounded-full px-2 py-0.5 text-xs text-neutral-400 ring-1 ring-inset ring-neutral-700 hover:text-neutral-100"
          title="Compare versions side by side"
        >
          ⇔ Compare
        </RouterLink>
      </div>

      <span
        v-if="archivedBy !== null"
        class="rounded-full bg-neutral-800 px-2 py-0.5 text-[11px] text-neutral-400"
        :title="`Variant ${archivedBy} was approved for this slot`"
      >
        Superseded by variant {{ archivedBy }}
      </span>

      <span class="flex items-center gap-1.5 text-xs font-medium text-neutral-300">
        <span
          class="size-1.5 rounded-full"
          :class="statusPill.tone === 'violet' ? 'animate-pulse' : ''"
          :style="{
            background: { green: '#9FE1CB', amber: '#FAC775', violet: '#a3a3a8' }[statusPill.tone],
          }"
        />
        {{ statusPill.label }}
      </span>

      <div v-if="versions.length > 1" class="flex items-center gap-1">
        <RouterLink
          v-for="entry in versions"
          :key="entry.id"
          :to="{ name: 'review', params: { projectId, imageId: entry.id } }"
          class="rounded-full px-2 py-0.5 font-mono text-xs ring-1 ring-inset"
          :class="
            entry.id === imageId
              ? 'bg-neutral-100 text-neutral-900 ring-neutral-100'
              : 'text-neutral-400 ring-neutral-700 hover:text-neutral-100'
          "
        >
          v{{ entry.version }}
        </RouterLink>
      </div>

      <div class="ml-auto flex items-center gap-3 text-xs text-neutral-400">
        <span>{{ activeSummary.open }} open</span>
        <span>{{ activeSummary.closed }} closed</span>

        <label
          v-if="can('submit_fix')"
          class="cursor-pointer rounded border border-neutral-600 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-800"
        >
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="hidden"
            @change="onFixSelected($event.target.files)"
          />
          {{ uploading ? 'Uploading…' : 'Submit fix' }}
        </label>

        <button
          v-if="can('approve_image')"
          type="button"
          :disabled="!everythingClosed || approved"
          class="rounded-md bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
          @click="onApprove"
        >
          {{ approved ? 'Approved' : 'Approve' }}
        </button>
      </div>
    </header>

    <!-- Phase 9: placement advisories — per-platform row under the status header.
         Advisory forever: nothing here can block approval. -->
    <div
      v-if="placement && placement.findings.length"
      class="flex flex-wrap items-center gap-2 border-b border-neutral-800 bg-neutral-900/40 px-4 py-1.5"
    >
      <span class="text-[11px] font-medium text-neutral-300">{{ placement.label }}</span>
      <template v-for="finding in placement.findings" :key="finding.key">
        <span
          class="flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px]"
          :class="
            finding.decision
              ? 'border-neutral-700 text-neutral-500 line-through decoration-neutral-600'
              : 'border-warning/50 text-warning'
          "
          :title="finding.decision ? `${finding.decision} — advisory closed` : finding.detail"
        >
          {{ finding.detail }}
          <template v-if="!finding.decision && can('comment')">
            <button
              type="button"
              class="text-neutral-400 hover:text-neutral-100"
              title="Noted — I'll deal with it"
              @click="onDecidePlacement(finding.key, 'acknowledged')"
            >
              ✓
            </button>
            <button
              type="button"
              class="text-neutral-400 hover:text-neutral-100"
              title="Waive — fine for this asset"
              @click="onDecidePlacement(finding.key, 'waived')"
            >
              ✕
            </button>
          </template>
        </span>
      </template>
      <button
        type="button"
        class="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-300 hover:bg-neutral-800"
        :class="placementOverlay ? 'bg-neutral-800 text-neutral-100' : ''"
        @click="placementOverlay = !placementOverlay"
      >
        {{ placement.label }} crop preview
      </button>
    </div>

    <!-- The crop + safe-area at honest scale: what the platform keeps, what its UI covers. -->
    <div
      v-if="placementOverlay && placement && placement.crop"
      class="border-b border-neutral-800 bg-neutral-900/40 px-4 py-3"
    >
      <div
        class="relative mx-auto max-h-72 overflow-hidden rounded"
        :style="{ aspectRatio: activeImage.image.width / activeImage.image.height, maxWidth: '24rem' }"
      >
        <img :src="activeImage.original_url" class="absolute inset-0 h-full w-full" />
        <!-- everything the crop discards, dimmed -->
        <div
          class="absolute inset-0"
          :style="{
            background: 'rgba(0,0,0,0.65)',
            clipPath: `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0,
              ${(placement.crop.left / activeImage.image.width) * 100}% ${(placement.crop.top / activeImage.image.height) * 100}%,
              ${(placement.crop.left / activeImage.image.width) * 100}% ${((placement.crop.top + placement.crop.height) / activeImage.image.height) * 100}%,
              ${((placement.crop.left + placement.crop.width) / activeImage.image.width) * 100}% ${((placement.crop.top + placement.crop.height) / activeImage.image.height) * 100}%,
              ${((placement.crop.left + placement.crop.width) / activeImage.image.width) * 100}% ${(placement.crop.top / activeImage.image.height) * 100}%,
              ${(placement.crop.left / activeImage.image.width) * 100}% ${(placement.crop.top / activeImage.image.height) * 100}%)`,
          }"
        />
        <!-- the platform's own UI zone: inside the crop but outside the safe area -->
        <div
          class="absolute border-2 border-dashed border-teal-300/80"
          :style="{
            left: `${(placement.safe.left / activeImage.image.width) * 100}%`,
            top: `${(placement.safe.top / activeImage.image.height) * 100}%`,
            width: `${(placement.safe.width / activeImage.image.width) * 100}%`,
            height: `${(placement.safe.height / activeImage.image.height) * 100}%`,
          }"
        />
      </div>
      <p class="mt-1.5 text-center text-[10px] text-neutral-500">
        dimmed = lost to the {{ placement.label }} crop · dashed = safe from the platform's own UI
      </p>
    </div>

    <div class="grid min-h-0 flex-1 lg:grid-cols-[1fr_23rem]">
      <!-- Video column (decision 23): the player is the canvas, the timeline the pins -->
      <div
        v-if="activeImage.image.kind === 'video'"
        class="flex min-h-0 flex-col gap-2 p-3"
      >
        <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg bg-black">
          <video
            ref="player"
            :src="activeImage.video_url"
            :poster="activeImage.original_url"
            controls
            class="h-full w-full object-contain"
          />
        </div>
        <!-- defects live ON the timeline: amber ranges at their timestamps -->
        <div v-if="timedDefects.length" class="px-1">
          <div class="relative h-2 rounded bg-neutral-800">
            <button
              v-for="defect in timedDefects"
              :key="defect.id"
              type="button"
              class="absolute top-0 h-2 rounded bg-warning/80 hover:bg-warning"
              :style="{
                left: `${(defect.time_start / (activeImage.image.duration || 1)) * 100}%`,
                width: `${Math.max(1.5, ((defect.time_end - defect.time_start) / (activeImage.image.duration || 1)) * 100)}%`,
              }"
              :title="`pin ${defect.pin} · ${timecode(defect.time_start)}–${timecode(defect.time_end)} — ${defect.comment}`"
              @click="seekTo(defect.time_start, defect.id)"
            />
          </div>
          <div class="mt-1 flex flex-wrap gap-1.5">
            <button
              v-for="defect in timedDefects"
              :key="`chip-${defect.id}`"
              type="button"
              class="rounded-full border px-2 py-0.5 text-[10px]"
              :class="
                selectedId === defect.id
                  ? 'border-neutral-300 text-neutral-100'
                  : 'border-neutral-700 text-neutral-400 hover:text-neutral-200'
              "
              @click="seekTo(defect.time_start, defect.id)"
            >
              {{ defect.pin }} · {{ timecode(defect.time_start) }}
            </button>
          </div>
        </div>
        <p v-if="typeof activeImage.image.loudness_lufs === 'number'" class="px-1 text-[10px] text-neutral-500">
          audio: {{ activeImage.image.loudness_lufs.toFixed(1) }} LUFS measured at ingest
        </p>
      </div>

      <!-- Canvas column: the image contain-fits — the rail is the only thing that scrolls -->
      <div v-else class="flex min-h-0 flex-col gap-2 p-3">
        <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg">
          <ReviewCanvas
            v-if="shown"
            ref="canvas"
            :src="shown.src"
            :width="shown.width"
            :height="shown.height"
            :defects="defects"
            :threads="threads"
            :pending-shapes="pendingShapes"
            :tool="tool"
            :color="color"
            :selected-id="selectedId"
            :hovered-id="hoveredId"
            @select="onCanvasSelect"
            @shape="onShape"
          />

          <!-- Drawing toolbar -->
          <div
            v-if="can('comment')"
            class="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-lg border border-neutral-700 bg-neutral-900/90 p-1 backdrop-blur"
          >
            <button
              v-for="entry in tools"
              :key="entry.id"
              type="button"
              class="rounded p-1.5 transition"
              :class="tool === entry.id ? 'bg-neutral-700 text-white' : 'text-neutral-400 hover:text-neutral-100'"
              :aria-label="entry.label"
              :title="entry.label"
              @click="tool = entry.id"
            >
              <svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.8">
                <path v-if="entry.id === 'select'" :d="entry.icon" stroke-linejoin="round" />
                <circle v-else-if="entry.id === 'circle'" cx="12" cy="12" r="8" />
                <rect v-else-if="entry.id === 'rect'" x="4" y="6" width="16" height="12" rx="1" />
                <path v-else-if="entry.id === 'arrow'" d="M5 19L19 5m0 0h-8m8 0v8" stroke-linecap="round" stroke-linejoin="round" />
                <path v-else d="M4 17c3-6 5 4 8-3s5 1 8-5" stroke-linecap="round" />
              </svg>
            </button>

            <span class="mx-1 h-5 w-px bg-neutral-700" />

            <button
              v-for="swatch in colors"
              :key="swatch"
              type="button"
              class="p-1.5"
              :aria-label="`Colour ${swatch}`"
              @click="color = swatch"
            >
              <span
                class="block size-3.5 rounded-full ring-2 transition"
                :style="{ background: swatch }"
                :class="color === swatch ? 'ring-white' : 'ring-transparent'"
              />
            </button>
          </div>
        </div>

        <!-- Composer: every comment anchors to a drawing -->
        <div v-if="can('comment')" class="rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
          <div class="flex items-center gap-2">
            <span
              v-if="pendingShapes.length"
              class="flex items-center gap-1.5 rounded-full bg-blue-500/15 px-2 py-0.5 text-xs text-blue-300 ring-1 ring-inset ring-blue-500/40"
            >
              {{ pendingShapes.length }} drawing{{ pendingShapes.length > 1 ? 's' : '' }} attached
              <button type="button" class="hover:text-white" aria-label="Clear drawings" @click="pendingShapes = []">×</button>
            </span>
            <span v-else class="text-xs text-neutral-500">
              Draw on the image to anchor your comment —
              <kbd class="rounded border border-neutral-700 px-1">c</kbd> circle
              <kbd class="rounded border border-neutral-700 px-1">r</kbd> rect
              <kbd class="rounded border border-neutral-700 px-1">a</kbd> arrow
              <kbd class="rounded border border-neutral-700 px-1">p</kbd> pen
              · scroll zooms · <kbd class="rounded border border-neutral-700 px-1">j/k</kbd> next/prev
            </span>
          </div>

          <div class="mt-2 flex items-end gap-2">
            <textarea
              ref="composer"
              v-model="composerBody"
              rows="1"
              placeholder="Leave a comment…"
              class="min-h-9 flex-1 resize-none rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-neutral-500"
              @keydown.enter.exact.prevent="postThread"
            />

            <button
              v-if="can('ask_agent')"
              type="button"
              class="flex items-center gap-1.5 rounded border px-3 py-2 text-xs font-medium transition"
              :class="
                askAgent
                  ? 'border-neutral-300 bg-neutral-50/10 text-neutral-100'
                  : 'border-neutral-700 text-neutral-400 hover:text-neutral-100'
              "
              @click="askAgent = !askAgent"
            >
              <svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" stroke-linejoin="round" />
              </svg>
              Ask agent
            </button>

            <button
              type="button"
              :disabled="posting || !composerBody.trim() || !pendingShapes.length"
              class="rounded bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
              @click="postThread"
            >
              {{ posting ? 'Posting…' : 'Post' }}
            </button>
          </div>

          <p v-if="askAgent" class="mt-1.5 text-xs text-neutral-400">
            The agent will inspect the drawn region, reply in this thread, and file a defect if it
            confirms one.
          </p>
        </div>

        <p v-if="notice" class="shrink-0 rounded bg-neutral-800/70 px-2 py-1.5 text-sm text-neutral-200">{{ notice }}</p>
      </div>

      <!-- Rail -->
      <aside class="flex min-h-0 flex-col border-l border-neutral-800">
        <nav class="flex gap-4 border-b border-neutral-800 px-4 pt-3 text-sm">
          <button
            v-for="entry in [
              { id: 'comments', label: `Comments ${railItems.length}` },
              { id: 'activity', label: 'Activity' },
              { id: 'rejected', label: `Rejected ${dismissals.length}` },
            ]"
            :key="entry.id"
            type="button"
            class="border-b-2 pb-2 transition"
            :class="
              tab === entry.id
                ? 'border-neutral-100 font-medium text-neutral-100'
                : 'border-transparent text-neutral-500 hover:text-neutral-300'
            "
            @click="tab = entry.id"
          >
            {{ entry.label }}
          </button>

          <label v-if="tab === 'comments'" class="ml-auto flex items-center gap-1.5 pb-2 text-xs text-neutral-500">
            <input v-model="openOnly" type="checkbox" class="accent-neutral-100" />
            Open only
          </label>
        </nav>

        <div class="min-h-0 flex-1 overflow-y-auto">
          <!-- The agent finished while the user was working — quiet, dismissible -->
          <div
            v-if="finishedNotice"
            class="flex items-center gap-2 border-b border-edge bg-panel px-3 py-2"
          >
            <span class="size-1.5 rounded-full" style="background: #9fe1cb" />
            <span class="min-w-0 truncate text-xs text-neutral-200">{{ finishedNotice }}</span>
            <button
              v-if="tab !== 'comments'"
              type="button"
              class="ml-auto shrink-0 text-xs text-neutral-400 hover:text-white"
              @click="((tab = 'comments'), (finishedNotice = ''))"
            >
              View
            </button>
            <button
              type="button"
              class="shrink-0 text-neutral-500 hover:text-white"
              :class="tab === 'comments' ? 'ml-auto' : ''"
              aria-label="Dismiss"
              @click="finishedNotice = ''"
            >
              ×
            </button>
          </div>

          <!-- Comments tab: one rail, agent and humans together -->
          <template v-if="tab === 'comments'">
            <!-- Phase 14: voice as an input mode for the agent's questions.
                 The control exists only while questions are open, and hides
                 itself the moment the backend says voice is unavailable. -->
            <div
              v-if="openQuestions.length && can('comment') && !voiceHidden"
              class="border-b border-neutral-800/70 px-3 py-2.5"
            >
              <button
                v-if="!voiceSession"
                type="button"
                class="w-full rounded-md border border-violet-500/40 px-3 py-1.5 text-xs text-violet-200 transition hover:bg-violet-500/10"
                @click="startVoice"
              >
                🎙 Talk through {{ openQuestions.length }} question{{ openQuestions.length === 1 ? '' : 's' }}
              </button>
              <VoicePanel
                v-else
                :session="voiceSession"
                @answer="onVoiceAnswer"
                @navigate="onVoiceNavigate"
                @closed="voiceSession = null"
              />
            </div>

            <div v-if="railItems.length" class="divide-y divide-neutral-800/70">
              <article
                v-for="item in railItems"
                :key="item.id"
                class="cursor-pointer border-l-2 px-3 py-2.5 transition"
                :class="selectedId === item.id ? 'bg-neutral-900/70' : 'border-l-transparent hover:bg-neutral-900/40'"
                :style="selectedId === item.id ? { borderLeftColor: pinColor(item) } : {}"
                @click="select(item)"
                @mouseenter="hoveredId = item.id"
                @mouseleave="hoveredId = ''"
              >
                <!-- Shared header: pin, author, state, age -->
                <div class="flex items-center gap-2">
                  <span
                    class="flex size-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-black"
                    :style="{ background: pinColor(item), opacity: item.open ? 1 : 0.5 }"
                  >
                    {{ item.pin }}
                  </span>
                  <span
                    class="truncate text-xs font-medium"
                    :class="item.kind === 'defect' ? 'text-neutral-100' : ''"
                  >
                    {{ item.kind === 'defect' ? 'QA agent' : item.thread.author_name }}
                  </span>
                  <template v-if="item.kind === 'defect'">
                    <SeverityChip :severity="item.defect.severity" />
                    <SeverityChip v-if="item.defect.status !== 'open'" :status="item.defect.status" />
                  </template>
                  <template v-else>
                    <span
                      v-if="item.thread.resolved"
                      class="rounded-full bg-green-500/15 px-1.5 py-px text-[10px] text-green-300 ring-1 ring-inset ring-green-500/40"
                    >
                      Resolved
                    </span>
                    <span v-if="agentStateLabel(item.thread)" class="text-[10px] text-neutral-400">
                      {{ agentStateLabel(item.thread) }}
                    </span>
                  </template>
                  <span class="ml-auto shrink-0 text-[10px] text-neutral-600">
                    {{ ago(item.kind === 'defect' ? item.defect.created_at : item.thread.created_at) }}
                  </span>
                </div>

                <!-- Agent defect -->
                <template v-if="item.kind === 'defect'">
                  <p
                    class="mt-1 text-sm text-neutral-200"
                    :class="selectedId === item.id ? '' : 'line-clamp-2'"
                  >
                    {{ item.defect.comment }}
                  </p>
                  <p v-if="selectedId === item.id" class="mt-1 text-[11px] text-neutral-500">
                    {{ item.defect.category }} · cells {{ item.defect.cells.join(', ') }}
                    <template v-if="item.defect.rule_ref"> · {{ item.defect.rule_ref }}</template>
                  </p>

                  <div
                    v-if="selectedId === item.id && thread && thread.defect.id === item.id"
                    @click.stop
                  >
                    <DefectThread
                      :thread="thread"
                      :can-propose="can('propose_memory_rule')"
                      @comment="onComment"
                      @transition="onTransition"
                      @propose-memory="onProposeMemory"
                      @answer="onAnswer"
                    />
                  </div>
                </template>

                <!-- Human thread -->
                <template v-else>
                  <p
                    class="mt-1 whitespace-pre-wrap text-sm text-neutral-200"
                    :class="selectedId === item.id ? '' : 'line-clamp-2'"
                  >
                    {{ item.comments[0]?.body }}
                  </p>
                  <p
                    v-if="selectedId !== item.id && item.comments.length > 1"
                    class="mt-1 text-[11px] text-neutral-500"
                  >
                    {{ item.comments.length - 1 }} repl{{ item.comments.length - 1 > 1 ? 'ies' : 'y' }}
                  </p>

                  <template v-if="selectedId === item.id">
                    <div
                      v-if="item.comments.length > 1"
                      class="mt-2 space-y-2 border-l border-neutral-800 pl-2.5"
                    >
                      <div v-for="entry in item.comments.slice(1)" :key="entry.id" class="text-sm">
                        <div class="flex items-baseline gap-2">
                          <span class="text-xs font-medium" :class="entry.is_agent ? 'text-neutral-100' : ''">
                            {{ entry.author_name }}
                          </span>
                          <span class="text-[10px] text-neutral-600">{{ ago(entry.created_at) }}</span>
                        </div>
                        <p class="mt-0.5 whitespace-pre-wrap text-neutral-300">{{ entry.body }}</p>
                      </div>
                    </div>

                    <div class="mt-2" @click.stop>
                      <div class="flex gap-2">
                        <input
                          v-model="replyDrafts[item.id]"
                          placeholder="Reply…"
                          class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2.5 py-1.5 text-sm outline-none focus:border-neutral-500"
                          @keydown.enter.prevent="sendReply(item)"
                        />
                        <button
                          type="button"
                          class="rounded border border-neutral-700 px-2.5 text-xs hover:bg-neutral-800"
                          @click="sendReply(item)"
                        >
                          Reply
                        </button>
                      </div>
                      <button
                        type="button"
                        class="mt-1.5 text-[11px] text-neutral-500 hover:text-neutral-200"
                        @click="resolveThread(projectId, item.id, !item.thread.resolved)"
                      >
                        {{ item.thread.resolved ? 'Reopen thread' : 'Mark resolved' }}
                      </button>
                    </div>
                  </template>
                </template>
              </article>
            </div>

            <div v-else class="p-6 text-center text-sm text-neutral-500">
              <template v-if="agentWorking">
                The agent is reviewing this image — findings land here as they're confirmed.
                You can already zoom, draw, and comment.
              </template>
              <template v-else>
                Nothing here yet. The agent's findings and your annotations will appear together.
              </template>
            </div>
          </template>

          <!-- Activity tab: this image's provenance, live while the agent works -->
          <div v-else-if="tab === 'activity'" class="p-3">
            <div
              v-if="agentWorking"
              class="mb-3 flex items-center gap-2 rounded-md border border-edge px-3 py-2"
            >
              <span class="size-1.5 animate-pulse rounded-full bg-neutral-300" />
              <span class="text-xs text-neutral-400">
                Agent reviewing this image — keep working, it won't interrupt you.
              </span>
            </div>
            <ActivityFeed
              :events="imageActivity"
              :streaming="streaming"
              empty="No agent activity recorded for this image in this session."
            />
          </div>

          <!-- Rejected tab: what the agent considered and threw out -->
          <div v-else class="p-3">
            <p class="mb-3 text-xs text-neutral-500">
              Regions the scanner flagged that did not survive a closer look — kept so you can judge
              how careful the agent is being.
            </p>
            <ul v-if="dismissals.length" class="space-y-3">
              <li v-for="dismissal in dismissals" :key="dismissal.id" class="text-sm">
                <div class="flex items-baseline gap-2">
                  <span class="font-mono text-xs text-neutral-500">{{ dismissal.cells.join(', ') }}</span>
                  <span class="text-xs text-neutral-600">{{ dismissal.stage === 'pro_gate' ? 'Final review' : 'Inspector' }}</span>
                </div>
                <p v-if="dismissal.hypothesis" class="mt-0.5 text-neutral-500">
                  Suspected: {{ dismissal.hypothesis }}
                </p>
                <p class="mt-0.5 text-neutral-300">{{ dismissal.reason }}</p>
              </li>
            </ul>
            <p v-else class="text-sm text-neutral-500">Nothing was rejected on this image.</p>
          </div>
        </div>
      </aside>
    </div>
  </div>

  <p v-else class="p-10 text-sm text-neutral-500">Loading…</p>
</template>
