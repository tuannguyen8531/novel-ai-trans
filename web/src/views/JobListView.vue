<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import { useJobsStore } from '@/stores/jobs'
import JobMonitor from '@/components/JobMonitor.vue'

const jobs = useJobsStore()
const selectedId = ref<string | null>(null)

onMounted(() => {
  jobs.refresh()
  jobs.startPolling()
})

onUnmounted(() => {
  jobs.stopPolling()
})

const rows = computed(() => {
  const list: Array<{ id: string; kind: string; novel: string | null; status: string; created_at: string; progress: Record<string, unknown> }> = []
  if (jobs.current) {
    list.push({
      id: jobs.current.id,
      kind: jobs.current.kind,
      novel: jobs.current.novel,
      status: jobs.current.status,
      created_at: jobs.current.created_at,
      progress: jobs.current.progress
    })
  }
  for (const job of jobs.history) {
    list.push({
      id: job.id,
      kind: job.kind,
      novel: job.novel,
      status: job.status,
      created_at: job.created_at,
      progress: job.progress
    })
  }
  return list
})

function statusBadge(status: string): string {
  if (status === 'completed') return 'ok'
  if (status === 'failed') return 'danger'
  if (status === 'cancelled' || status === 'cancelling') return 'warn'
  return ''
}

function progressFor(row: { progress: Record<string, unknown>; status: string }) {
  if (row.status === 'completed' || row.status === 'failed' || row.status === 'cancelled') {
    return null
  }
  const current = Number(row.progress.current ?? 0)
  const total = Number(row.progress.total ?? 0)
  if (!total) return null
  return {
    current,
    total,
    pct: Math.min(100, (current / total) * 100),
    chapter: typeof row.progress.chapter === 'number' ? (row.progress.chapter as number) : null
  }
}

function select(id: string) {
  selectedId.value = id
  jobs.follow(id)
}
</script>

<template>
  <section class="flex-col gap-3">
    <div class="card">
      <div class="row" style="justify-content: space-between;">
        <h2>Jobs</h2>
        <button class="secondary" type="button" @click="jobs.refresh()">Refresh</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Kind</th>
            <th>Novel</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td><code>{{ row.id.slice(0, 8) }}</code></td>
            <td>{{ row.kind }}</td>
            <td>{{ row.novel ?? '—' }}</td>
            <td><span class="badge" :class="statusBadge(row.status)">{{ row.status }}</span></td>
            <td class="progress-cell">
              <template v-if="progressFor(row)">
                <div class="row" style="justify-content: space-between; font-size: 0.8rem;">
                  <span class="muted">
                    <template v-if="progressFor(row)?.chapter !== null">Ch. {{ progressFor(row)?.chapter }} · </template>
                    {{ progressFor(row)?.current }} / {{ progressFor(row)?.total }} ({{ progressFor(row)?.pct.toFixed(0) }}%)
                  </span>
                </div>
                <div class="progress" style="margin-top: 0.2rem;">
                  <div class="fill" :style="{ width: (progressFor(row)?.pct ?? 0) + '%' }"></div>
                </div>
              </template>
              <span v-else class="muted">—</span>
            </td>
            <td class="muted">{{ new Date(row.created_at).toLocaleString() }}</td>
            <td>
              <button class="secondary" type="button" @click="select(row.id)">Open</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="7" class="muted">No jobs yet.</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="selectedId" class="card">
      <h3>Job {{ selectedId.slice(0, 8) }}</h3>
      <JobMonitor :job-id="selectedId" />
    </div>
  </section>
</template>
