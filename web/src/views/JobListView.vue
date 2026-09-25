<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import {
  Activity,
  RotateCw,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  X
} from '@lucide/vue'
import { useJobsStore } from '@/composables/jobs'
import JobMonitor from '@/components/JobMonitor.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import CustomSelect from '@/components/common/CustomSelect.vue'
import { formatDateTime } from '@/datetime'
import type { JobModel } from '@/api/types'
import { formatJobKind, t } from '@/i18n'

const jobs = useJobsStore()
const selectedId = ref<string | null>(null)
const statusFilter = ref<'all' | JobModel['status']>('all')
const statusOptions = computed<Array<{ value: 'all' | JobModel['status']; label: string }>>(() => [
  { value: 'all', label: t('all_statuses') },
  { value: 'queued', label: t('queued') },
  { value: 'running', label: t('running') },
  { value: 'completed', label: t('completed') },
  { value: 'degraded', label: t('degraded') },
  { value: 'failed', label: t('failed') },
  { value: 'cancelling', label: t('cancelling') },
  { value: 'cancelled', label: t('cancelled') }
])
const TERMINAL_STATUSES = new Set<JobModel['status']>([
  'completed',
  'degraded',
  'failed',
  'cancelled'
])

onMounted(() => {
  void jobs.refresh()
  jobs.startPolling()
})

onUnmounted(() => {
  jobs.stopPolling()
})

const allRows = computed(() => {
  const list: Array<{ id: string; kind: string; novel: string | null; status: JobModel['status']; created_at: string; progress: Record<string, unknown> }> = []
  for (const job of jobs.activeJobs) {
    list.push({
      id: job.id,
      kind: job.kind,
      novel: job.novel,
      status: job.status,
      created_at: job.created_at,
      progress: job.progress
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

const rows = computed(() => (
  statusFilter.value === 'all'
    ? allRows.value
    : allRows.value.filter((row) => row.status === statusFilter.value)
))

// Operational Summary Counts
const runningCount = computed(() => allRows.value.filter((r) => ['running', 'queued', 'cancelling'].includes(r.status)).length)
const completedCount = computed(() => allRows.value.filter((r) => r.status === 'completed').length)
const failedCount = computed(() => allRows.value.filter((r) => ['failed', 'degraded'].includes(r.status)).length)

function isTerminal(status: JobModel['status']): boolean {
  return TERMINAL_STATUSES.has(status)
}

function progressFor(row: { progress: Record<string, unknown>; status: JobModel['status'] }) {
  if (isTerminal(row.status)) {
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
    await jobs.remove(deleteJobId.value)
    if (selectedId.value === deleteJobId.value) {
      selectedId.value = null
    }
    showDeleteDialog.value = false
  } catch (err) {
    alert((err as Error).message)
  } finally {
    deleteJobSaving.value = false
    deleteJobId.value = null
  }
}

const hasInactiveJobs = computed(() => {
  return allRows.value.some((row) => isTerminal(row.status))
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
    await jobs.clear()
    showClearDialog.value = false
    if (selectedId.value && !allRows.value.some((r) => r.id === selectedId.value)) {
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
  <div class="jobs-view-root">
    <!-- Header Controls -->
    <header class="jobs-header card-panel">
      <div class="header-left">
        <div class="header-icon-box">
          <Activity :size="22" />
        </div>
        <div>
          <h2 class="jobs-title">{{ $t("operations_jobs") }}</h2>
          <p class="jobs-subtitle">
            {{ $t("job_monitor_description") }}
          </p>
        </div>
      </div>

      <div class="header-right">
        <div class="status-filter-wrap">
          <span class="filter-label">{{ $t("filter") }}</span>
          <CustomSelect
            v-model="statusFilter"
            :options="statusOptions"
            class="status-custom-select"
          />
        </div>

        <button
          class="secondary btn-refresh"
          type="button"
          :title="$t('refresh_job_lists')"
          @click="jobs.refresh()"
        >
          <RotateCw :size="15" />
          <span>{{ $t("refresh") }}</span>
        </button>

        <button
          v-if="hasInactiveJobs"
          class="secondary btn-clear-all"
          type="button"
          :title="$t('remove_all_inactive_history_jobs')"
          @click="confirmClearAll"
        >
          <Trash2 :size="15" />
          <span>{{ $t("clear_history") }}</span>
        </button>
      </div>
    </header>

    <!-- Operational Stat Cards -->
    <div class="metrics-row">
      <div class="stat-pill-card" :class="{ 'has-running': runningCount > 0 }">
        <div class="stat-icon-wrap" :class="{ pulse: runningCount > 0 }">
          <Activity :size="18" />
        </div>
        <div class="stat-text">
          <span class="stat-num">{{ runningCount }}</span>
          <span class="stat-lbl">{{ $t("active_operations") }}</span>
        </div>
      </div>

      <div class="stat-pill-card">
        <div class="stat-icon-wrap success">
          <CheckCircle2 :size="18" />
        </div>
        <div class="stat-text">
          <span class="stat-num">{{ completedCount }}</span>
          <span class="stat-lbl">{{ $t("completed") }}</span>
        </div>
      </div>

      <div class="stat-pill-card">
        <div class="stat-icon-wrap" :class="{ danger: failedCount > 0 }">
          <AlertTriangle :size="18" />
        </div>
        <div class="stat-text">
          <span class="stat-num">{{ failedCount }}</span>
          <span class="stat-lbl">{{ $t("failed_degraded") }}</span>
        </div>
      </div>
    </div>

    <!-- Main Table Card -->
    <div class="card-panel table-shell">
      <table class="jobs-table">
        <thead>
          <tr>
            <th style="width: 100px;">{{ $t("job_id") }}</th>
            <th>{{ $t("type") }}</th>
            <th>{{ $t("novel") }}</th>
            <th>{{ $t("status") }}</th>
            <th>{{ $t("progress") }}</th>
            <th>{{ $t("timestamp") }}</th>
            <th style="text-align: right;">{{ $t("action") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            :class="{ 'row-selected': selectedId === row.id }"
            @click="select(row.id)"
          >
            <td>
              <code class="job-id-cell">{{ row.id.slice(0, 8) }}</code>
            </td>
            <td>
              <span class="kind-tag">{{ formatJobKind(row.kind) }}</span>
            </td>
            <td>
              <span class="novel-cell" :title="row.novel ?? $t('none')">
                {{ row.novel ?? '—' }}
              </span>
            </td>
            <td>
              <StatusBadge :status="row.status" size="sm" />
            </td>
            <td class="progress-col">
              <template v-if="progressFor(row)">
                <div class="progress-details-row">
                  <span class="progress-ch">
                    <template v-if="progressFor(row)?.chapter !== null">
                      {{ $t("chapter_position", { chapter: progressFor(row)?.chapter ?? 0, current: progressFor(row)?.current ?? 0, total: progressFor(row)?.total ?? 0 }) }}
                    </template>
                    <template v-else>
                      {{ $t("current_of_total", { current: progressFor(row)?.current ?? 0, total: progressFor(row)?.total ?? 0 }) }}
                    </template>
                  </span>
                  <span class="progress-pct">{{ progressFor(row)?.pct.toFixed(0) }}%</span>
                </div>
                <div class="progress">
                  <div class="fill" :style="{ width: `${progressFor(row)?.pct ?? 0}%` }" />
                </div>
              </template>
              <span v-else class="muted">—</span>
            </td>
            <td class="timestamp-cell">
              {{ formatDateTime(row.created_at) }}
            </td>
            <td style="text-align: right;">
              <div class="table-actions-row" @click.stop>
                <button
                  type="button"
                  class="secondary btn-inspect"
                  :class="{ active: selectedId === row.id }"
                  @click="select(row.id)"
                >
                  <span>{{ $t("inspect") }}</span>
                  <ChevronRight :size="13" />
                </button>
                <button
                  v-if="isTerminal(row.status)"
                  type="button"
                  class="btn-icon-subtle danger"
                  :title="$t('delete_job')"
                  @click="confirmDelete(row.id)"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="7" class="empty-table-msg">
              {{ allRows.length ? $t('no_jobs_match_this_status_filter') : $t('no_recorded_jobs_yet') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Selected Job Inspector -->
    <div v-if="selectedId" class="card-panel inspector-card">
      <div class="inspector-header">
        <div class="inspector-title">
          <Activity :size="18" class="inspect-icon" />
          <h3>{{ $t("inspector_id", { id: selectedId }) }}</h3>
        </div>
        <button
          type="button"
          class="btn-close-inspect"
          :aria-label="$t('close_inspector')"
          @click="selectedId = null"
        >
          <X :size="16" />
        </button>
      </div>

      <JobMonitor :job-id="selectedId" />
    </div>

    <!-- Confirm Dialogs -->
    <ConfirmDialog
      :show="showDeleteDialog"
      :title="$t('delete_job_history')"
      :message="$t('confirm_delete_job', { id: deleteJobId?.slice(0, 8) ?? '' })"
      :confirm-label="$t('delete_job')"
      :danger="true"
      :loading="deleteJobSaving"
      @confirm="handleDelete"
      @cancel="cancelDelete"
    />

    <ConfirmDialog
      :show="showClearDialog"
      :title="$t('delete_all_inactive_jobs')"
      :message="$t('confirm_clear_job_history')"
      :confirm-label="$t('clear_all_history')"
      :danger="true"
      :loading="clearSaving"
      @confirm="handleClearAll"
      @cancel="cancelClearAll"
    />
  </div>
</template>

<style scoped>
.jobs-view-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.jobs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-lg);
  background: var(--accent-subtle);
  border: 1px solid rgba(79, 125, 249, 0.25);
  color: var(--accent);
  flex-shrink: 0;
}

.jobs-title {
  margin: 0;
  font-size: 1.45rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.jobs-subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: var(--fg-secondary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.status-filter-wrap {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0;
}

.filter-label {
  font-size: 0.825rem;
  color: var(--fg-muted);
}

.status-custom-select {
  min-width: 9.5rem;
}

.btn-refresh,
.btn-clear-all {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.825rem;
  padding: 0.45rem 0.85rem;
}

.btn-clear-all {
  color: var(--danger);
  border-color: rgba(244, 63, 94, 0.3);
}

.btn-clear-all:hover:not(:disabled) {
  background: var(--danger-subtle);
  border-color: var(--danger);
}

/* Metrics Row */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 1rem;
}

.stat-pill-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-subtle);
  transition: border-color var(--transition-fast);
}

.stat-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  color: var(--fg-secondary);
}

.stat-icon-wrap.success {
  background: var(--ok-subtle);
  color: var(--ok);
}

.stat-icon-wrap.danger {
  background: var(--danger-subtle);
  color: var(--danger);
}

.stat-pill-card.has-running .stat-icon-wrap {
  background: var(--accent-subtle);
  color: var(--accent);
}

.stat-text {
  display: flex;
  flex-direction: column;
}

.stat-num {
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.2;
  color: var(--fg-primary);
}

.stat-lbl {
  font-size: 0.75rem;
  color: var(--fg-secondary);
}

/* Table Shell */
.table-shell {
  padding: 0;
  overflow-x: auto;
}

.jobs-table {
  width: 100%;
}

.jobs-table tbody tr {
  cursor: pointer;
}

.jobs-table tbody tr.row-selected {
  background: var(--bg-surface-elevated);
}

.job-id-cell {
  font-size: 0.8rem;
  font-weight: 600;
}

.kind-tag {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-xs);
  background: var(--bg-surface-elevated);
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: capitalize;
}

.novel-cell {
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}

.progress-col {
  min-width: 130px;
}

.progress-details-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.75rem;
  margin-bottom: 0.25rem;
}

.progress-ch {
  color: var(--fg-muted);
}

.progress-pct {
  color: var(--accent);
  font-weight: 600;
}

.timestamp-cell {
  font-size: 0.8rem;
  color: var(--fg-muted);
  white-space: nowrap;
}

.table-actions-row {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.btn-inspect {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.775rem;
  padding: 0.25rem 0.6rem;
}

.btn-inspect.active {
  background: var(--accent);
  color: #ffffff;
  border-color: transparent;
}

.empty-table-msg {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--fg-muted);
}

/* Inspector Card */
.inspector-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border: 1px solid var(--border-hover);
  animation: modal-fade-in 0.2s ease;
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-base);
}

.inspector-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.inspect-icon {
  color: var(--accent);
}

.inspector-title h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--fg-primary);
}

.btn-close-inspect {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-close-inspect:hover {
  color: var(--fg-primary);
  background: transparent;
}
</style>
