<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, useId, watch } from 'vue'
import type { ChapterPostCheck } from '@/api/types'

const props = defineProps<{
  open: boolean
  review: ChapterPostCheck | null
  loading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  close: []
  reviewItem: [key: string, ignored: boolean]
  acceptCandidate: [candidateHash: string, overwrite: boolean]
}>()

const dialog = ref<HTMLElement | null>(null)
const confirmingOverwrite = ref(false)
const titleId = useId()
let previousFocus: HTMLElement | null = null

const candidateAcceptable = computed(() => (
  props.review?.candidate_translation !== null &&
  Boolean(props.review?.candidate_translation.trim()) &&
  props.review?.partial === false &&
  Boolean(props.review?.candidate_hash)
))

function formatCode(code: string): string {
  return code.replaceAll('_', ' ')
}

function close() {
  if (!props.loading) emit('close')
}

function requestCandidateAcceptance() {
  const review = props.review
  if (!review?.candidate_hash || !candidateAcceptable.value) return
  if (review.previous_output_exists) {
    confirmingOverwrite.value = true
    return
  }
  emit('acceptCandidate', review.candidate_hash, false)
}

function confirmCandidateOverwrite() {
  const candidateHash = props.review?.candidate_hash
  if (candidateHash) emit('acceptCandidate', candidateHash, true)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => dialog.value?.focus())
  } else {
    document.body.style.overflow = ''
    previousFocus?.focus()
    previousFocus = null
  }
})

watch(
  [() => props.open, () => props.review?.candidate_hash],
  () => { confirmingOverwrite.value = false }
)

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <div v-if="open" class="modal-overlay" @click.self="close">
    <div
      ref="dialog"
      class="modal-card post-check-dialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      tabindex="-1"
      @keydown="handleKeydown"
    >
      <header class="modal-header">
        <div>
          <h3 :id="titleId">Post-check Review</h3>
          <p v-if="review" class="muted dialog-subtitle">
            Chapter {{ review.chapter }} · {{ review.target.toUpperCase() }}
          </p>
        </div>
        <button
          type="button"
          class="modal-close"
          aria-label="Close"
          :disabled="loading"
          @click="close"
        >&times;</button>
      </header>

      <div class="modal-body">
        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="loading && !review" class="muted">Loading post-check results...</p>
        <p v-else-if="!review?.items.length" class="muted">No post-check issues for this chapter.</p>

        <div v-else class="review-table-wrap">
          <table class="review-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Check</th>
                <th>Details</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in review.items" :key="item.key">
                <td>
                  <span :class="['badge', item.severity === 'error' ? 'danger' : 'warn']">
                    {{ item.severity }}
                  </span>
                </td>
                <td class="check-code">{{ formatCode(item.code) }}</td>
                <td class="check-detail">
                  <code v-if="item.code === 'contains_source_language_chars' && item.origin === 'output'">
                    {{ item.detail }}
                  </code>
                  <span v-else>{{ item.detail }}</span>
                </td>
                <td>
                  <span v-if="item.ignored" class="badge ok">ignored</span>
                  <span v-else-if="item.origin === 'rejected'" class="badge danger">failed</span>
                  <span v-else class="badge warn">active</span>
                </td>
                <td class="review-action">
                  <button
                    v-if="item.reviewable"
                    type="button"
                    class="secondary"
                    :disabled="loading"
                    @click="emit('reviewItem', item.key, !item.ignored)"
                  >
                    {{ item.ignored ? 'Restore' : 'Ignore' }}
                  </button>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <details v-if="review && review.candidate_translation !== null" class="candidate">
          <summary>
            Rejected candidate
            <span v-if="review?.partial" class="muted">
              (partial, failed at chunk {{ (review.failed_chunk_index ?? 0) + 1 }}/{{ review.total_chunks }})
            </span>
          </summary>
          <pre>{{ review?.candidate_translation || '(empty translation)' }}</pre>
          <div v-if="candidateAcceptable" class="candidate-actions">
            <template v-if="confirmingOverwrite">
              <p class="candidate-warning">
                This replaces the current translated chapter. The existing output remains safe until publication commits.
              </p>
              <div class="candidate-buttons">
                <button
                  type="button"
                  class="secondary"
                  :disabled="loading"
                  @click="confirmingOverwrite = false"
                >Keep current output</button>
                <button
                  type="button"
                  class="danger"
                  :disabled="loading"
                  @click="confirmCandidateOverwrite"
                >{{ loading ? 'Publishing...' : 'Replace output' }}</button>
              </div>
            </template>
            <template v-else>
              <p class="muted">
                Accepting publishes this candidate without running learning, summary, or glossary updates.
              </p>
              <button type="button" :disabled="loading" @click="requestCandidateAcceptance">
                {{ loading ? 'Publishing...' : 'Accept candidate' }}
              </button>
            </template>
          </div>
        </details>
      </div>

      <footer class="modal-footer">
        <button type="button" class="secondary" :disabled="loading" @click="close">Close</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
}

.modal-card {
  display: flex;
  flex-direction: column;
  width: min(70rem, 100%);
  max-height: 88vh;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
}

.modal-header,
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
}

.modal-header {
  border-bottom: 1px solid var(--border);
}

.modal-header h3,
.dialog-subtitle {
  margin: 0;
}

.dialog-subtitle {
  margin-top: 0.2rem;
  font-size: 0.85rem;
}

.modal-close {
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
  color: var(--fg-dim);
  font-size: 1.5rem;
  line-height: 1;
  background: transparent;
  border: 0;
}

.modal-body {
  flex: 1;
  padding: 1.25rem;
  overflow: auto;
}

.modal-footer {
  justify-content: flex-end;
  border-top: 1px solid var(--border);
}

.review-table-wrap {
  overflow-x: auto;
}

.review-table {
  width: 100%;
  min-width: 48rem;
}

.review-table th {
  vertical-align: top;
}

.review-table td {
  vertical-align: middle;
}

.check-code {
  max-width: 14rem;
  text-transform: none;
}

.check-detail {
  min-width: 16rem;
  white-space: normal;
}

.review-action {
  text-align: right;
}

.candidate {
  margin-top: 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.candidate summary {
  padding: 0.75rem 1rem;
  cursor: pointer;
}

.candidate pre {
  max-height: 24rem;
  margin: 0;
  padding: 1rem;
  overflow: auto;
  color: var(--fg);
  font: inherit;
  line-height: 1.65;
  white-space: pre-wrap;
  border-top: 1px solid var(--border);
}

.candidate-actions {
  padding: 1rem;
  border-top: 1px solid var(--border);
}

.candidate-actions p {
  margin: 0 0 0.75rem;
}

.candidate-warning {
  color: var(--danger);
}

.candidate-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
