<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import { useJobsStore } from '@/stores/jobs'
import JobMonitor from '@/components/JobMonitor.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

import { api } from '@/api/client'

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

const showDeleteDialog = ref(false)
const deleteJobId = ref<string | null>(null)
const deleteJobSaving = ref(false)

function confirmDelete(id: string) {
  deleteJobId.value = id
  showDeleteDialog.value = true
}

function cancelDelete() {
  showDeleteDialog.value = false
  deleteJobId.value = null
}

async function handleDelete() {
  if (!deleteJobId.value) return
  deleteJobSaving.value = true
  try {
    await api.deleteJob(deleteJobId.value)
    if (selectedId.value === deleteJobId.value) {
      selectedId.value = null
    }
    showDeleteDialog.value = false
    await jobs.refresh()
  } catch (err) {
    alert((err as Error).message)
  } finally {
    deleteJobSaving.value = false
    deleteJobId.value = null
  }
}

const hasInactiveJobs = computed(() => {
  return rows.value.some((row) => ['completed', 'failed', 'cancelled'].includes(row.status))
})

const showClearDialog = ref(false)
const clearSaving = ref(false)

function confirmClearAll() {
  showClearDialog.value = true
}

function cancelClearAll() {
  showClearDialog.value = false
}

async function handleClearAll() {
  clearSaving.value = true
  try {
    await api.clearJobs()
    showClearDialog.value = false
    await jobs.refresh()
    if (selectedId.value && !rows.value.some((r) => r.id === selectedId.value)) {
      selectedId.value = null
    }
  } catch (err) {
    alert((err as Error).message)
  } finally {
    clearSaving.value = false
  }
}
</script>

<template>
  <section class="flex-col gap-3">
    <div class="card">
      <div class="row" style="justify-content: space-between; align-items: center;">
        <h2>Jobs</h2>
        <div class="row gap-2">
          <button
            v-if="hasInactiveJobs"
            class="secondary"
            style="color: var(--danger);"
            type="button"
            @click="confirmClearAll"
          >Delete All</button>
          <button class="secondary" type="button" @click="jobs.refresh()">Refresh</button>
        </div>
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
              <div class="row gap-2" style="align-items: center;">
                <button class="secondary" type="button" @click="select(row.id)">Open</button>
                <button
                  v-if="['completed', 'failed', 'cancelled'].includes(row.status)"
                  class="secondary"
                  style="color: var(--danger);"
                  type="button"
                  @click="confirmDelete(row.id)"
                >Delete</button>
              </div>
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

    <ConfirmDialog
      :show="showDeleteDialog"
      title="Delete Job"
      :message="`Delete job '${deleteJobId?.slice(0, 8)}'?\n\nThis permanently removes the job logs and history. This cannot be undone.`"
      confirm-label="Delete"
      :danger="true"
      :loading="deleteJobSaving"
      @confirm="handleDelete"
      @cancel="cancelDelete"
    />

    <ConfirmDialog
      :show="showClearDialog"
      title="Delete All Inactive Jobs"
      message="Are you sure you want to delete all completed, failed, and cancelled jobs?\n\nThis permanently removes all their logs and history. This cannot be undone."
      confirm-label="Delete All"
      :danger="true"
      :loading="clearSaving"
      @confirm="handleClearAll"
      @cancel="cancelClearAll"
    />
  </section>
</template>
