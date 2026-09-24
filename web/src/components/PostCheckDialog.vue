<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { X } from '@lucide/vue'
import type { ChapterPostCheck } from '@/api/types'
import { formatLanguage } from '@/language'
import { useBodyScrollLock } from '@/composables/scrolllock'

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

useBodyScrollLock(() => props.open)

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
    void nextTick(() => dialog.value?.focus())
  } else {
    previousFocus?.focus()
    previousFocus = null
  }
})

watch(
  [() => props.open, () => props.review?.candidate_hash],
  () => { confirmingOverwrite.value = false }
)

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
          <h3 :id="titleId">{{ $t("post_check_review") }}</h3>
          <p v-if="review" class="muted dialog-subtitle">
            {{ $t("chapter_language", { chapter: review.chapter, language: formatLanguage(review.target) }) }}
          </p>
        </div>
        <button
          type="button"
          class="modal-close"
          :aria-label="$t('close')"
          :disabled="loading"
          @click="close"
        >
          <X :size="18" />
        </button>
      </header>

      <div class="modal-body">
        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="loading && !review" class="muted">{{ $t("loading_post_check_results") }}</p>
        <p v-else-if="!review?.items.length" class="muted">{{ $t("no_post_check_issues_for_this_chapter") }}</p>

        <div v-else class="review-table-wrap">
          <table class="review-table">
            <thead>
              <tr>
                <th class="col-severity">{{ $t("severity") }}</th>
                <th class="col-check">{{ $t("check") }}</th>
                <th class="col-detail">{{ $t("details") }}</th>
                <th class="col-status">{{ $t("status") }}</th>
                <th class="col-action" style="text-align: right;">{{ $t("action") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in review.items" :key="item.key">
                <td class="col-severity">
                  <span :class="['badge', item.severity === 'error' ? 'danger' : 'warn']">
                    {{ item.severity }}
                  </span>
                </td>
                <td class="check-code col-check">{{ formatCode(item.code) }}</td>
                <td class="check-detail col-detail">
                  <code v-if="item.code === 'contains_source_language_chars' && item.origin === 'output'">
                    {{ item.detail }}
                  </code>
                  <span v-else>{{ item.detail }}</span>
                </td>
                <td class="col-status">
                  <span v-if="item.ignored" class="badge ok">{{ $t("ignored") }}</span>
                  <span v-else-if="item.origin === 'rejected'" class="badge danger">{{ $t("failed") }}</span>
                  <span v-else class="badge warn">{{ $t("active") }}</span>
                </td>
                <td class="review-action col-action">
                  <button
                    v-if="item.reviewable"
                    type="button"
                    class="secondary btn-review-action"
                    :disabled="loading"
                    @click="emit('reviewItem', item.key, !item.ignored)"
                  >
                    {{ item.ignored ? $t('restore') : $t('ignore') }}
                  </button>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <details v-if="review && review.candidate_translation !== null" class="candidate">
          <summary>
            {{ $t("rejected_candidate") }}
            <span v-if="review?.partial" class="muted">
              {{ $t("chunk_translation_failed", { chunk: (review.failed_chunk_index ?? 0) + 1, total: review.total_chunks ?? 0 }) }}
            </span>
          </summary>
          <pre>{{ review?.candidate_translation || $t('empty_translation') }}</pre>
          <div v-if="candidateAcceptable" class="candidate-actions">
            <template v-if="confirmingOverwrite">
              <p class="candidate-warning">
                {{ $t("translation_publish_explanation") }}
              </p>
              <div class="candidate-buttons">
                <button
                  type="button"
                  class="secondary"
                  :disabled="loading"
                  @click="confirmingOverwrite = false"
                >{{ $t("keep_current_output") }}</button>
                <button
                  type="button"
                  class="danger"
                  :disabled="loading"
                  @click="confirmCandidateOverwrite"
                >{{ loading ? $t('publishing') : $t('replace_output') }}</button>
              </div>
            </template>
            <template v-else>
              <p class="muted">
                {{ $t("accept_candidate_explanation") }}
              </p>
              <button type="button" :disabled="loading" @click="requestCandidateAcceptance">
                {{ loading ? $t('publishing') : $t('accept_candidate') }}
              </button>
            </template>
          </div>
        </details>
      </div>

      <footer class="modal-footer">
        <button type="button" class="secondary" :disabled="loading" @click="close">{{ $t("close") }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.post-check-dialog {
  width: min(68rem, 94vw);
  max-width: min(68rem, 94vw);
  max-height: 90vh;
}

.dialog-subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  color: var(--fg-muted);
}

.review-table-wrap {
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  overflow-x: auto;
  background: var(--bg-surface);
}

.review-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.review-table th {
  padding: 0.85rem 1.15rem;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-muted);
  background: var(--bg-surface-elevated);
  border-bottom: 1px solid var(--border-base);
  text-align: left;
  white-space: nowrap;
}

.review-table td {
  padding: 0.85rem 1.15rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--fg-primary);
  vertical-align: middle;
  font-size: 0.875rem;
}

.review-table tbody tr:last-child td {
  border-bottom: none;
}

.review-table tbody tr {
  transition: background-color var(--transition-fast);
}

.review-table tbody tr:hover {
  background-color: var(--bg-surface-elevated);
}

.col-severity {
  width: 6.5rem;
  white-space: nowrap;
}

.col-check {
  width: 14rem;
}

.check-code {
  font-weight: 500;
  color: var(--fg-primary);
  text-transform: capitalize;
}

.col-detail {
  min-width: 12rem;
}

.check-detail {
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.5;
  color: var(--fg-secondary);
}

.check-detail code {
  display: inline-block;
  max-width: 100%;
  padding: 0.25rem 0.5rem;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xs);
  font-size: 0.825rem;
  color: var(--danger);
  white-space: pre-wrap;
  word-break: break-all;
}

.col-status {
  width: 6.5rem;
  white-space: nowrap;
}

.col-action {
  width: 6.5rem;
  text-align: right;
  white-space: nowrap;
}

.review-action {
  text-align: right;
}

.btn-review-action {
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
  border-radius: var(--radius-sm);
}

.candidate {
  margin-top: 1rem;
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  overflow: hidden;
}

.candidate summary {
  padding: 0.85rem 1.25rem;
  cursor: pointer;
  font-weight: 600;
  color: var(--fg-primary);
  background: var(--bg-surface-elevated);
  transition: background-color var(--transition-fast);
  user-select: none;
}

.candidate summary:hover {
  background: var(--bg-surface-active);
}

.candidate pre {
  max-height: 22rem;
  margin: 0;
  padding: 1.25rem;
  overflow: auto;
  color: var(--fg-primary);
  font-family: var(--font-serif);
  font-size: 0.95rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--bg-surface-subtle);
  border-top: 1px solid var(--border-base);
}

.candidate-actions {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border-base);
  background: var(--bg-surface);
}

.candidate-actions p {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
}

.candidate-warning {
  color: var(--danger);
}

.candidate-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
