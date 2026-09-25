<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { X } from '@lucide/vue'
import type { GlossaryApplyResponse, GlossaryReplacementReport } from '@/api/types'
import { formatLanguage } from '@/language'
import { useBodyScrollLock } from '@/composables/scrolllock'
import { t } from '@/i18n'

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

useBodyScrollLock(() => props.open)

const busy = computed(() => props.applyLoading || props.rollbackLoading)

function close() {
  if (busy.value) return
  emit('update:open', false)
}

async function handleRollback() {
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
  if (props.previewData?.write && replacement.status === 'safe') return t('applied')
  const labels: Record<string, string> = {
    safe: 'safe',
    applied: 'applied',
    already_applied: 'already_applied',
    ambiguous: 'ambiguous',
    missing_output: 'missing_output',
    conflict: 'conflict'
  }
  return t(labels[replacement.status] ?? replacement.status).toUpperCase()
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    void nextTick(() => modalCard.value?.focus())
  } else {
    previousFocus?.focus()
    previousFocus = null
  }
})

watch(busy, (isBusy) => {
  if (isBusy) void nextTick(() => modalCard.value?.focus())
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
        <h3 id="glossary-preview-title">{{ $t("preview_apply_glossary_changes") }}</h3>
        <button
          type="button"
          class="modal-close"
          :aria-label="$t('close_glossary_preview')"
          :disabled="busy"
          @click="close"
        >
          <X :size="18" />
        </button>
      </header>
      <div class="modal-body">
        <p v-if="error" class="error">{{ error }}</p>
        <div v-if="previewLoading" class="preview-spinner">
          <p>{{ $t("scanning_translated_chapters") }}</p>
        </div>
        <div v-else-if="previewData">
          <div class="preview-summary">
            <p>
              {{ $t("novel_target_language", { novel: previewData.novel, language: formatLanguage(previewData.target) }) }}
            </p>
            <p>{{ $t("chapters_to_update_count", { count: previewData.changed_files }) }}</p>
            <p v-if="previewData.conflicted" class="error">
              {{ $t("translation_conflict_warning") }}
            </p>
            <p v-else-if="previewData.write" class="notice">
              {{ previewData.changed_files === 1
                ? $t("single_chapter_updated")
                : $t("chapters_updated", { count: previewData.changed_files }) }}
              <template v-if="unresolvedCount">
                {{ unresolvedCount === 1
                  ? $t("single_pending_issue")
                  : $t("pending_issues_count", { count: unresolvedCount }) }}
              </template>
            </p>
          </div>

          <div v-if="previewData.replacements.length" class="preview-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{{ $t("chapter") }}</th>
                  <th>{{ $t("kind") }}</th>
                  <th>{{ $t("original") }}</th>
                  <th>{{ $t("old_translation") }}</th>
                  <th>{{ $t("new_translation") }}</th>
                  <th>{{ $t("status") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(replacement, index) in previewData.replacements" :key="index">
                  <td>{{ $t("chapter_number", { number: replacement.chapter }) }}</td>
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
            {{ $t("no_matching_translated_text") }}
          </p>
        </div>
      </div>
      <footer class="modal-footer">
        <button
          v-if="previewData?.backup_id"
          type="button"
          class="secondary"
          :disabled="busy"
          @click="handleRollback"
        >
          {{ rollbackLoading ? $t('restoring') : $t('restore_previous_version') }}
        </button>
        <button type="button" class="secondary" :disabled="busy" @click="close">
          {{ previewData?.write ? $t('close') : $t('cancel') }}
        </button>
        <button
          v-if="previewData && !previewLoading && !previewData.write"
          type="button"
          :disabled="previewData.conflicted || applyLoading"
          @click="apply"
        >
          {{ applyLoading ? $t('applying') : $t('confirm_apply') }}
        </button>
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
