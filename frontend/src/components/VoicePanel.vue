<script>
// Voice on question threads (phase 14): the browser talks straight to the Live
// API with a server-minted constrained token. Every tool call the model makes
// comes back here, and this component executes it by emitting to the review
// page — which calls the exact same store action as the buttons. A spoken
// answer IS the clicked one; the model never holds credentials to our API.
//
// NOTE: this client has not yet been exercised against the real Live service
// (needs credentials — see Deferred evidence in the implementation plan). It
// fails closed: any error tears the session down and the buttons remain.

const LIVE_WS =
  'wss://generativelanguage.googleapis.com/ws/' +
  'google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'

const INPUT_RATE = 16000
const OUTPUT_RATE = 24000

export default {
  name: 'VoicePanel',
  props: {
    session: { type: Object, required: true }, // { token, model, question_ids }
  },
  emits: ['answer', 'navigate', 'closed'],
  data() {
    return {
      status: 'connecting', // connecting | listening | error
      lines: [], // the visible record of what the session did
      error: '',
    }
  },
  mounted() {
    this.start()
  },
  beforeUnmount() {
    this.teardown()
  },
  methods: {
    async start() {
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      } catch {
        this.fail('Microphone unavailable')
        return
      }
      this.socket = new WebSocket(
        `${LIVE_WS}?access_token=${encodeURIComponent(this.session.token)}`,
      )
      this.socket.onopen = () => {
        // Constraints ride the token; the setup only names the model.
        this.socket.send(
          JSON.stringify({ setup: { model: `models/${this.session.model}` } }),
        )
        this.startMic()
        this.status = 'listening'
        this.lines.push('Listening — talk through the questions.')
      }
      this.socket.onmessage = (event) => this.onMessage(event)
      this.socket.onerror = () => this.fail('Voice connection failed')
      this.socket.onclose = () => {
        if (this.status !== 'error') this.$emit('closed')
      }
    },

    startMic() {
      this.audioIn = new AudioContext({ sampleRate: INPUT_RATE })
      const source = this.audioIn.createMediaStreamSource(this.stream)
      // ScriptProcessor is deprecated but universal; a worklet is polish, not risk.
      this.processor = this.audioIn.createScriptProcessor(4096, 1, 1)
      this.processor.onaudioprocess = (event) => {
        if (this.socket?.readyState !== WebSocket.OPEN) return
        const samples = event.inputBuffer.getChannelData(0)
        const pcm = new Int16Array(samples.length)
        for (let i = 0; i < samples.length; i += 1) {
          pcm[i] = Math.max(-1, Math.min(1, samples[i])) * 0x7fff
        }
        this.socket.send(
          JSON.stringify({
            realtimeInput: {
              mediaChunks: [
                {
                  mimeType: `audio/pcm;rate=${INPUT_RATE}`,
                  data: this.toBase64(pcm.buffer),
                },
              ],
            },
          }),
        )
      }
      source.connect(this.processor)
      this.processor.connect(this.audioIn.destination)
    },

    async onMessage(event) {
      const raw = event.data instanceof Blob ? await event.data.text() : event.data
      let message
      try {
        message = JSON.parse(raw)
      } catch {
        return
      }
      for (const part of message.serverContent?.modelTurn?.parts || []) {
        if (part.inlineData?.data) this.playAudio(part.inlineData.data)
      }
      for (const call of message.toolCall?.functionCalls || []) {
        this.onToolCall(call)
      }
    },

    /** The model's whole authority arrives here: record an answer, or move. */
    onToolCall(call) {
      let response = { result: 'ok' }
      if (call.name === 'answer_question') {
        const { defect_id: defectId, confirmed } = call.args || {}
        if (this.session.question_ids.includes(defectId)) {
          this.$emit('answer', { defectId, confirmed: Boolean(confirmed) })
          this.lines.push(
            `Recorded: ${confirmed ? "it's real" : 'not a problem'} (${defectId})`,
          )
        } else {
          response = { result: 'error', message: 'unknown question id' }
        }
      } else if (call.name === 'next_question' || call.name === 'previous_question') {
        this.$emit('navigate', call.name === 'next_question' ? 1 : -1)
      } else {
        response = { result: 'error', message: 'not a tool of this session' }
      }
      this.socket?.send(
        JSON.stringify({
          toolResponse: {
            functionResponses: [{ id: call.id, name: call.name, response }],
          },
        }),
      )
    },

    playAudio(base64) {
      if (!this.audioOut) {
        this.audioOut = new AudioContext({ sampleRate: OUTPUT_RATE })
        this.playhead = 0
      }
      const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
      const pcm = new Int16Array(bytes.buffer)
      const buffer = this.audioOut.createBuffer(1, pcm.length, OUTPUT_RATE)
      const channel = buffer.getChannelData(0)
      for (let i = 0; i < pcm.length; i += 1) channel[i] = pcm[i] / 0x8000
      const node = this.audioOut.createBufferSource()
      node.buffer = buffer
      node.connect(this.audioOut.destination)
      this.playhead = Math.max(this.playhead, this.audioOut.currentTime)
      node.start(this.playhead)
      this.playhead += buffer.duration
    },

    toBase64(arrayBuffer) {
      let binary = ''
      const bytes = new Uint8Array(arrayBuffer)
      for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i])
      return btoa(binary)
    },

    fail(message) {
      this.status = 'error'
      this.error = message
      this.teardown()
    },

    teardown() {
      this.processor?.disconnect()
      this.audioIn?.close().catch(() => {})
      this.audioOut?.close().catch(() => {})
      this.stream?.getTracks().forEach((track) => track.stop())
      if (this.socket && this.socket.readyState === WebSocket.OPEN) this.socket.close()
      this.socket = null
    },
  },
}
</script>

<template>
  <div class="rounded-lg border border-violet-500/40 bg-violet-500/5 p-3 text-xs">
    <div class="flex items-center gap-2">
      <span
        class="size-1.5 rounded-full"
        :class="status === 'listening' ? 'animate-pulse bg-violet-400' : 'bg-neutral-500'"
      />
      <span class="font-medium text-violet-200">
        {{ status === 'error' ? error : 'Talking through the questions' }}
      </span>
      <button
        type="button"
        class="ml-auto rounded-md border border-edge-strong px-2 py-0.5 text-neutral-300 hover:bg-edge"
        @click="$emit('closed')"
      >
        Stop
      </button>
    </div>
    <ul v-if="lines.length" class="mt-2 space-y-1 text-neutral-400">
      <li v-for="(line, index) in lines" :key="index">{{ line }}</li>
    </ul>
    <p class="mt-2 text-[10px] text-neutral-500">
      The voice can only record your answers — approval stays yours, on this page.
    </p>
  </div>
</template>
