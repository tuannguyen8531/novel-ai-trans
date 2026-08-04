<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useJobsStore } from '@/composables/jobs'
import type { JobModel } from '@/api/types'

const props = withDefaults(defineProps<{ job?: JobModel; jobId?: string; live?: boolean }>(), {
  live: true
})
const jobs = useJobsStore()
const error = ref<string | null>(null)
const consoleLog = ref<HTMLElement | null>(null)
const cancellingRequest = ref(false)

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

const statusBadge = computed(() => {
  const status = localJob.value?.status
  if (status === 'completed') return 'ok'
  if (status === 'failed') return 'danger'
  if (status === 'cancelled' || status === 'cancelling') return 'warn'
  return ''
})

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
</script>

<template>
  <div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="!localJob" class="muted">Loading job…</div>
    <div v-else>
      <div class="row" style="justify-content: space-between;">
        <div>
          <strong>{{ localJob.kind }}</strong>
          <span class="muted"> · {{ localJob.novel ?? '—' }}</span>
        </div>
        <span class="badge" :class="statusBadge">{{ localJob.status }}</span>
      </div>
      <div v-if="progress && progress.total > 0" style="margin-top: 0.5rem;">
        <div class="row" style="justify-content: space-between;">
          <span class="muted">
            <span v-if="progress.chapter">Ch. {{ progress.chapter }} · </span>
            {{ progress.current }} / {{ progress.total }} ({{ progress.pct.toFixed(0) }}%)
          </span>
        </div>
        <div class="progress" style="margin-top: 0.3rem;">
          <div class="fill" :style="{ width: progress.pct + '%' }"></div>
        </div>
      </div>
      <p v-if="progress?.message" class="muted" style="margin-top: 0.3rem;">{{ progress.message }}</p>
      <div class="row gap-2" style="margin-top: 0.5rem;">
        <button
          v-if="localJob.kind !== 'insert' && ['running', 'queued', 'cancelling'].includes(localJob.status)"
          class="secondary"
          type="button"
          :disabled="cancellingRequest || localJob.status === 'cancelling'"
          @click="cancel"
        >
          {{ cancellingRequest || localJob.status === 'cancelling' ? 'Cancelling…' : 'Cancel' }}
        </button>
      </div>
      <details v-if="localJob.result" style="margin-top: 0.5rem;">
        <summary class="muted">Result</summary>
        <pre class="job-log-content">{{ JSON.stringify(localJob.result, null, 2) }}</pre>
      </details>
      <details v-if="localJob.error" style="margin-top: 0.5rem;">
        <summary class="error">Error</summary>
        <pre class="job-log-content">{{ JSON.stringify(localJob.error, null, 2) }}</pre>
      </details>
      <details v-if="localJob.logs.length" open style="margin-top: 0.5rem;">
        <summary class="muted">Console ({{ localJob.logs.length }})</summary>
        <pre ref="consoleLog" class="job-log-content job-console-content">{{ localJob.logs.join('\n') }}</pre>
      </details>
    </div>
  </div>
</template>

<style scoped>
.job-log-content {
  background: var(--bg-elev-2);
  border-radius: var(--radius);
  padding: 0.5rem 0.75rem;
  margin-top: 0.4rem;
  max-height: 18rem;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.8rem;
}

.job-console-content {
  line-height: 1.35;
  height: calc(7 * 1.35em + 1rem);
  max-height: none;
}
</style>
