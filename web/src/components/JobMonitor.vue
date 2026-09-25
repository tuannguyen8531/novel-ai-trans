<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import {
  Terminal,
  Copy,
  Check,
  XCircle,
  AlertOctagon,
  FileCode,
  AlertTriangle
} from '@lucide/vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useJobsStore } from '@/composables/jobs'
import type { JobModel } from '@/api/types'
import { formatJobKind } from '@/i18n'

const props = withDefaults(defineProps<{ job?: JobModel; jobId?: string; live?: boolean }>(), {
  job: undefined,
  jobId: undefined,
  live: true
})
const jobs = useJobsStore()
const error = ref<string | null>(null)
const consoleLog = ref<HTMLElement | null>(null)
const cancellingRequest = ref(false)
const forceStoppingRequest = ref(false)
const showForceStopDialog = ref(false)
const copied = ref(false)

const jobId = computed(() => props.jobId ?? props.job?.id ?? null)
const followId = computed(() => props.live ? jobId.value : null)
const localJob = computed<JobModel | null>(() => {
  const id = jobId.value
  return (id ? jobs.findJob(id) : null) ?? props.job ?? null
})

onUnmounted(() => {
  jobs.closeStream(followId.value)
})

watch(
  followId,
  (id) => {
    if (id) {
      jobs.follow(id)
    }
  },
  { immediate: true }
)

watch(
  () => localJob.value?.logs.length ?? 0,
  async () => {
    await nextTick()
    if (consoleLog.value) {
      consoleLog.value.scrollTop = consoleLog.value.scrollHeight
    }
  }
)

const progress = computed(() => {
  if (!localJob.value) return null
  const p = localJob.value.progress
  const current = Number(p.current ?? 0)
  const total = Number(p.total ?? 0)
  const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0
  return { current, total, pct, chapter: p.chapter as number | undefined, message: p.message as string | undefined }
})

const canForceStop = computed(() => (
  localJob.value?.force_stoppable === true
  && ['running', 'cancelling'].includes(localJob.value.status)
))

async function cancel() {
  if (!jobId.value || cancellingRequest.value) return
  cancellingRequest.value = true
  error.value = null
  try {
    await jobs.cancel(jobId.value)
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    cancellingRequest.value = false
  }
}

async function forceStop() {
  if (!jobId.value || forceStoppingRequest.value) return
  forceStoppingRequest.value = true
  error.value = null
  try {
    await jobs.forceStop(jobId.value)
    showForceStopDialog.value = false
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    forceStoppingRequest.value = false
  }
}

async function copyLogs() {
  if (!localJob.value?.logs.length) return
  try {
    await navigator.clipboard.writeText(localJob.value.logs.join('\n'))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // fallback or ignore
  }
}
</script>

<template>
  <div class="job-monitor-root">
    <div v-if="error" class="alert-error">{{ error }}</div>
    <div v-else-if="!localJob" class="muted loading-hint">{{ $t("awaiting_job_status") }}</div>
    <div v-else class="monitor-content">
      <!-- Header Strip -->
      <div class="monitor-top-row">
        <div class="job-identity">
          <span class="job-kind-badge">{{ formatJobKind(localJob.kind) }}</span>
          <span v-if="localJob.novel" class="job-novel-tag">{{ localJob.novel }}</span>
          <code class="job-id-code">{{ localJob.id.slice(0, 8) }}</code>
        </div>
        <StatusBadge :status="localJob.status" />
      </div>

      <!-- Progress Section -->
      <div v-if="progress && progress.total > 0" class="monitor-progress-box">
        <div class="progress-labels">
          <span class="progress-message">
            <template v-if="progress.chapter">{{ $t("chapter_message", { chapter: progress.chapter, message: progress.message || $t('processing_chapters') }) }}</template>
            <template v-else>{{ progress.message || $t('processing_chapters') }}</template>
          </span>
          <span class="progress-count">
            <strong>{{ progress.current }}</strong> / {{ progress.total }}
            <span class="pct-num">({{ progress.pct.toFixed(0) }}%)</span>
          </span>
        </div>
        <div class="progress">
          <div class="fill" :style="{ width: `${progress.pct}%` }" />
        </div>
      </div>

      <!-- Action Controls -->
      <div
        v-if="['running', 'queued', 'cancelling'].includes(localJob.status)"
        class="monitor-actions-row"
      >
        <button
          v-if="localJob.kind !== 'insert'"
          class="secondary btn-cancel"
          type="button"
          :disabled="cancellingRequest || localJob.status === 'cancelling'"
          @click="cancel"
        >
          <XCircle :size="14" />
          <span>{{ cancellingRequest || localJob.status === 'cancelling' ? $t('cancelling') + '…' : $t('cancel_job') }}</span>
        </button>

        <button
          v-if="canForceStop"
          class="danger btn-force-stop"
          type="button"
          :disabled="forceStoppingRequest"
          @click="showForceStopDialog = true"
        >
          <AlertOctagon :size="14" />
          <span>{{ forceStoppingRequest ? $t('stopping') : $t('force_stop') }}</span>
        </button>
      </div>

      <!-- Error Payload -->
      <details v-if="localJob.error" class="details-accordion error-details">
        <summary class="details-summary error">
          <AlertTriangle :size="14" />
          <span>{{ $t("job_error_details") }}</span>
        </summary>
        <pre class="terminal-box error-box">{{ JSON.stringify(localJob.error, null, 2) }}</pre>
      </details>

      <!-- Result Payload -->
      <details v-if="localJob.result" class="details-accordion">
        <summary class="details-summary">
          <FileCode :size="14" />
          <span>{{ $t("execution_output_result") }}</span>
        </summary>
        <pre class="terminal-box">{{ JSON.stringify(localJob.result, null, 2) }}</pre>
      </details>

      <!-- Console Log Viewer -->
      <div v-if="localJob.logs.length" class="console-viewer-wrap">
        <div class="console-header">
          <div class="console-title">
            <Terminal :size="14" />
            <span>{{ $t("console_logs_lines", { count: localJob.logs.length }) }}</span>
          </div>
          <button
            type="button"
            class="btn-copy-logs"
            :title="$t('copy_logs_to_clipboard')"
            @click="copyLogs"
          >
            <Check v-if="copied" :size="13" />
            <Copy v-else :size="13" />
            <span>{{ copied ? $t('copied') : $t('copy') }}</span>
          </button>
        </div>
        <pre ref="consoleLog" class="terminal-box console-box">{{ localJob.logs.join('\n') }}</pre>
      </div>
    </div>

    <!-- Force Stop Dialog -->
    <ConfirmDialog
      :show="showForceStopDialog"
      :title="$t('force_stop_translation')"
      :message="$t('confirm_stop_translation')"
      :confirm-label="$t('force_stop')"
      :danger="true"
      :loading="forceStoppingRequest"
      @confirm="forceStop"
      @cancel="showForceStopDialog = false"
    />
  </div>
</template>

<style scoped>
.job-monitor-root {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.monitor-content {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.monitor-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.job-identity {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.job-kind-badge {
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--fg-primary);
  text-transform: capitalize;
}

.job-novel-tag {
  font-size: 0.85rem;
  color: var(--fg-secondary);
}

.job-id-code {
  font-size: 0.75rem;
}

.monitor-progress-box {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.progress-labels {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.8rem;
}

.progress-message {
  color: var(--fg-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-count {
  color: var(--fg-primary);
  flex-shrink: 0;
}

.pct-num {
  color: var(--accent);
  font-weight: 600;
}

.monitor-actions-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.btn-cancel,
.btn-force-stop {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  padding: 0.35rem 0.65rem;
}

/* Details Accordion */
.details-accordion {
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  overflow: hidden;
}

.details-summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 0.85rem;
  font-size: 0.825rem;
  font-weight: 600;
  color: var(--fg-secondary);
  cursor: pointer;
  user-select: none;
}

.details-summary:hover {
  color: var(--fg-primary);
}

.details-summary.error {
  color: var(--danger);
}

/* Terminal & Console */
.console-viewer-wrap {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  background: var(--bg-surface-subtle);
  overflow: hidden;
}

.console-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.45rem 0.75rem;
  background: var(--bg-surface-elevated);
  border-bottom: 1px solid var(--border-base);
}

.console-title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.775rem;
  font-weight: 600;
  color: var(--fg-secondary);
  font-family: var(--font-mono);
}

.btn-copy-logs {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-xs);
  background: var(--bg-surface-active);
  border: 1px solid var(--border-subtle);
  color: var(--fg-secondary);
  font-size: 0.725rem;
  cursor: pointer;
}

.btn-copy-logs:hover {
  color: var(--fg-primary);
  border-color: var(--border-hover);
}

.terminal-box {
  margin: 0;
  padding: 0.75rem 1rem;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.5;
  color: #a5b4fc;
  background: #090c10;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.console-box {
  height: 12rem;
  max-height: 18rem;
  overflow-y: auto;
}

.error-box {
  color: var(--danger);
  max-height: 12rem;
}

.alert-error {
  color: var(--danger);
  font-size: 0.85rem;
  padding: 0.5rem 0;
}

.loading-hint {
  padding: 1rem 0;
  font-size: 0.85rem;
}
</style>
