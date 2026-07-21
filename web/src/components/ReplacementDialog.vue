<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import type { GlossaryApplyResponse, GlossaryReplacementReport } from '@/api/types'

const props = defineProps<{
  open: boolean
  error: string | null
  previewLoading: boolean
  previewData: GlossaryApplyResponse | null
  applyLoading: boolean
  rollbackLoading: boolean
  unresolvedCount: number
  apply: () => Promise<void>
  rollback: () => Promise<boolean>
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const modalCard = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

const busy = computed(() => props.applyLoading || props.rollbackLoading)

function close() {
  if (busy.value) return
  emit('update:open', false)
}

async function rollback() {
  if (await props.rollback()) close()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key !== 'Tab' || !modalCard.value) return
  const focusable = Array.from(
    modalCard.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'
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

function statusClass(status: string) {
  if (status === 'safe' || status === 'applied' || status === 'already_applied') return 'ok'
  if (status === 'ambiguous' || status === 'missing_output') return 'warn'
  if (status === 'conflict') return 'danger'
  return ''
}

function statusLabel(replacement: GlossaryReplacementReport) {
  if (props.previewData?.write && replacement.status === 'safe') return 'APPLIED'
  return replacement.status.toUpperCase()
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => modalCard.value?.focus())
  } else {
    document.body.style.overflow = ''
    previousFocus?.focus()
    previousFocus = null
  }
})

watch(busy, (isBusy) => {
  if (isBusy) void nextTick(() => modalCard.value?.focus())
})

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <div v-if="open" class="modal-overlay">
    <div
      ref="modalCard"
      class="modal-card replacement-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="glossary-preview-title"
      tabindex="-1"
      @keydown="handleKeydown"
    >
      <header class="modal-header">
        <h3 id="glossary-preview-title">Preview & Apply Glossary Changes</h3>
        <button
          type="button"
          class="modal-close"
          aria-label="Close glossary preview"
          :disabled="busy"
          @click="close"
        >&times;</button>
      </header>
      <div class="modal-body">
        <p v-if="error" class="error">{{ error }}</p>
        <div v-if="previewLoading" class="preview-spinner">
          <p>Scanning translated chapters...</p>
        </div>
        <div v-else-if="previewData">
          <div class="preview-summary">
            <p>
              Novel: <strong>{{ previewData.novel }}</strong> |
              Target language: <strong>{{ previewData.target }}</strong>
            </p>
            <p>Chapters to update: <strong>{{ previewData.changed_files }}</strong></p>
            <p v-if="previewData.conflicted" class="error">
              ⚠️ Conflict detected. You cannot overwrite the translation while conflicts exist.
            </p>
            <p v-else-if="previewData.write" class="notice">
              Updated {{ previewData.changed_files }} chapter(s).
              <template v-if="unresolvedCount">{{ unresolvedCount }} issue(s) remain pending.</template>
            </p>
          </div>

          <div v-if="previewData.replacements.length" class="preview-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Chapter</th>
                  <th>Kind</th>
                  <th>Original</th>
                  <th>Old translation</th>
                  <th>New translation</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(replacement, index) in previewData.replacements" :key="index">
                  <td>Ch.{{ replacement.chapter }}</td>
                  <td>{{ replacement.kind }}</td>
                  <td>{{ replacement.sources.join('/') }}</td>
                  <td>{{ replacement.old }}</td>
                  <td>{{ replacement.new }}</td>
                  <td>
                    <span :class="['badge', statusClass(replacement.status)]">
                      {{ statusLabel(replacement) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted">
            No matching text was found in the translated chapters.
          </p>
        </div>
      </div>
      <footer class="modal-footer">
        <button
          v-if="previewData?.backup_id"
          type="button"
          class="secondary"
          :disabled="busy"
          @click="rollback"
        >{{ rollbackLoading ? 'Restoring...' : 'Restore previous version' }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="close">
          {{ previewData?.write ? 'Close' : 'Cancel' }}
        </button>
        <button
          v-if="previewData && !previewLoading && !previewData.write"
          type="button"
          :disabled="previewData.conflicted || applyLoading"
          @click="apply"
        >{{ applyLoading ? 'Applying...' : 'Confirm & Apply' }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.replacement-dialog {
  max-width: 44rem;
}

.preview-summary {
  margin-bottom: 1.25rem;
  padding: 0.75rem 1rem;
  background: var(--bg-elev-2);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.preview-summary p {
  margin: 0.25rem 0;
}

.preview-table-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  max-height: 25rem;
  overflow: auto;
}

.preview-spinner {
  padding: 3rem;
  text-align: center;
  color: var(--fg-dim);
}

.notice {
  color: var(--ok);
}
</style>
