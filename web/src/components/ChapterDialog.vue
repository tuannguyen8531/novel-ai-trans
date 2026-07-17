<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  show: boolean
  suggestedNumber: number
  saving: boolean
  error: string | null
}>()

const emit = defineEmits<{
  confirm: [chapter: number, content: string]
  cancel: []
}>()

const chapterNumber = ref<number | null>(null)
const content = ref('')
const modalCard = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

function requestCancel() {
  if (!props.saving) emit('cancel')
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    requestCancel()
    return
  }
  if (event.key !== 'Tab' || !modalCard.value) return
  const focusable = Array.from(
    modalCard.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
  )
  if (!focusable.length) {
    event.preventDefault()
    modalCard.value.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.show, (isOpen) => {
  if (isOpen) {
    chapterNumber.value = props.suggestedNumber
    content.value = ''
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => modalCard.value?.focus())
  } else {
    document.body.style.overflow = ''
    previousFocus?.focus()
    previousFocus = null
  }
})

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <div v-if="show" class="modal-overlay">
    <div
      ref="modalCard"
      class="modal-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-chapter-title"
      tabindex="-1"
      @keydown="handleKeydown"
    >
      <header class="modal-header">
        <h3 id="add-chapter-title">Add Chapter</h3>
        <button
          type="button"
          class="modal-close"
          aria-label="Close"
          :disabled="saving"
          @click="requestCancel"
        >&times;</button>
      </header>
      <div class="modal-body">
        <p v-if="error" class="error">{{ error }}</p>
        <div>
          <label>Chapter number</label>
          <input v-model.number="chapterNumber" type="number" min="1" />
        </div>
        <div class="content-field">
          <label>Content (optional)</label>
          <textarea v-model="content" class="chapter-edit-area"></textarea>
        </div>
      </div>
      <footer class="modal-footer">
        <button type="button" class="secondary" :disabled="saving" @click="requestCancel">Cancel</button>
        <button
          type="button"
          :disabled="saving || chapterNumber === null || chapterNumber < 1"
          @click="chapterNumber !== null && emit('confirm', chapterNumber, content)"
        >{{ saving ? 'Adding...' : 'Add' }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.content-field {
  margin-top: 0.75rem;
}

.chapter-edit-area {
  width: 100%;
  min-height: 12rem;
  max-height: 36rem;
  padding: 1rem 1.25rem;
  color: var(--fg);
  font-family: var(--font);
  font-size: 1rem;
  line-height: 1.6;
  resize: vertical;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
</style>
