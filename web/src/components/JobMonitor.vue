<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useJobsStore } from '@/stores/jobs'
import type { JobModel } from '@/api/types'

const props = defineProps<{ job?: JobModel; jobId?: string }>()
const jobs = useJobsStore()
const localJob = ref<JobModel | null>(props.job ?? null)
const error = ref<string | null>(null)

const followId = computed(() => props.jobId ?? props.job?.id ?? null)

function findLocal(id: string): JobModel | null {
  if (localJob.value?.id === id) return localJob.value
  if (jobs.current?.id === id) return jobs.current
  return jobs.history.find((j) => j.id === id) ?? null
}

onMounted(() => {
  if (followId.value) {
    jobs.follow(followId.value)
  }
})

onUnmounted(() => {
  jobs.closeStream()
})

watch(
  () => props.job,
  (value) => {
    if (value) {
      localJob.value = value
    }
  }
)

watch(
  () => [jobs.current, jobs.history] as const,
  () => {
    if (!followId.value) return
    const fresh = findLocal(followId.value)
    if (fresh) {
      localJob.value = fresh
    }
  },
  { deep: true }
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
  if (!followId.value) return
  await jobs.cancel(followId.value)
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
          v-if="['running', 'queued', 'cancelling'].includes(localJob.status)"
          class="secondary"
          type="button"
          @click="cancel"
        >
          Cancel
        </button>
      </div>
      <details v-if="localJob.result" style="margin-top: 0.5rem;">
        <summary class="muted">Result</summary>
        <pre class="chapter-content">{{ JSON.stringify(localJob.result, null, 2) }}</pre>
      </details>
      <details v-if="localJob.error" style="margin-top: 0.5rem;">
        <summary class="error">Error</summary>
        <pre class="chapter-content">{{ JSON.stringify(localJob.error, null, 2) }}</pre>
      </details>
      <details v-if="localJob.logs.length" style="margin-top: 0.5rem;">
        <summary class="muted">Logs ({{ localJob.logs.length }})</summary>
        <pre class="chapter-content">{{ localJob.logs.join('\n') }}</pre>
      </details>
    </div>
  </div>
</template>

<style scoped>
.chapter-content {
  background: var(--bg-elev-2);
  border-radius: var(--radius);
  padding: 0.5rem 0.75rem;
  margin-top: 0.4rem;
  max-height: 18rem;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.8rem;
}
</style>
