<script>
import { mapActions, mapState } from 'pinia'

import ActivityFeed from '@/components/ActivityFeed.vue'
import DefectThread from '@/components/DefectThread.vue'
import ReviewCanvas from '@/components/ReviewCanvas.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { isClear, sortDefects } from '@/domain/defects'
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
  components: { ActivityFeed, DefectThread, ReviewCanvas, SeverityChip },
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
      versions: [],
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
    statusPill() {
      if (this.activeImage?.image.approved_by) return { label: 'Approved', tone: 'green' }
      const { open, inFlight } = this.activeSummary
      if (inFlight) return { label: 'Agent re-checking', tone: 'violet' }
      if (open) return { label: 'Needs review', tone: 'amber' }
      return { label: 'Clear', tone: 'green' }
    },
    everythingClosed() {
      return isClear(this.defects)
    },
    approved() {
      return Boolean(this.activeImage?.image.approved_by)
    },
  },
  watch: {
    imageId() {
      this.load()
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
      'proposeMemoryRule',
      'approveImage',
      'submitFix',
      'createThread',
      'replyThread',
      'resolveThread',
      'startStream',
      'stopStream',
    ]),
    async load() {
      this.notice = ''
      this.selectedId = ''
      this.pendingShapes = []
      await useProjectsStore().fetchOne(this.projectId)
      await this.fetchImage(this.projectId, this.imageId)
      this.fetchThreads(this.projectId, this.imageId)
      this.fetchDismissals(this.projectId, this.imageId)
      this.versions = await this.fetchVersions(this.projectId, this.imageId)
      this.startStream(this.projectId)
      const first = this.railItems[0]
      if (first) this.select(first)
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
    async onProposeMemory(description) {
      const proposal = await this.proposeMemoryRule(this.projectId, this.selectedId, description)
      this.notice = proposal.collisions.length
        ? `Proposed — overlaps ${proposal.collisions.length} existing rule(s); the owner will reconcile.`
        : 'Proposed. The brand owner approves it before it takes effect.'
    },
    async onApprove() {
      try {
        await this.approveImage(this.projectId, this.imageId)
        this.notice = 'Approved.'
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
        this.notice = error.message
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
      <RouterLink
        :to="{ name: 'project', params: { projectId } }"
        class="text-neutral-400 hover:text-neutral-100"
        aria-label="Back to project"
      >
        <svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </RouterLink>

      <h2 class="truncate text-sm font-semibold">{{ activeImage.image.filename }}</h2>

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

    <div class="grid min-h-0 flex-1 lg:grid-cols-[1fr_23rem]">
      <!-- Canvas column: the image contain-fits — the rail is the only thing that scrolls -->
      <div class="flex min-h-0 flex-col gap-2 p-3">
        <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg">
          <ReviewCanvas
            ref="canvas"
            :src="activeImage.original_url"
            :width="activeImage.image.width"
            :height="activeImage.image.height"
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
          <!-- Comments tab: one rail, agent and humans together -->
          <template v-if="tab === 'comments'">
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
              Nothing here yet. The agent's findings and your annotations will appear together.
            </div>
          </template>

          <!-- Activity tab -->
          <div v-else-if="tab === 'activity'" class="p-3">
            <ActivityFeed :events="recentActivity" :streaming="streaming" />
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
