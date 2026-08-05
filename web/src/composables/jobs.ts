import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, getAuthToken } from '@/api/client'
import { openSse, type SseClient } from '@/api/sse'
import type { JobModel } from '@/api/types'

const ACTIVE_STATUSES = new Set<JobModel['status']>(['queued', 'running', 'cancelling'])
const TERMINAL_STATUSES = new Set<JobModel['status']>(['completed', 'degraded', 'failed', 'cancelled'])
const EVENT_STATUSES: Partial<Record<string, JobModel['status']>> = {
  queued: 'queued',
  started: 'running',
  cancelling: 'cancelling',
  completed: 'completed',
  degraded: 'degraded',
  failed: 'failed',
  cancelled: 'cancelled'
}
const POLL_INTERVAL_MS = 10_000

export const useJobsStore = defineStore('jobs', () => {
  const current = ref<JobModel | null>(null)
  const active = ref<JobModel[]>([])
  const activeJobs = computed(() => active.value.length ? active.value : (current.value ? [current.value] : []))
  const history = ref<JobModel[]>([])
  const events = ref<{ event: string, data: unknown, timestamp: string }[]>([])
  const error = ref<string | null>(null)
  const loading = ref(false)
  let activeStream: SseClient | null = null
  let activeStreamJobId: string | null = null
  let pollTimer: number | null = null
  let refreshSequence = 0
  let activeRefreshSequence = 0

  function isActive(job: JobModel | null): job is JobModel {
    return !!job && ACTIVE_STATUSES.has(job.status)
  }

  function findJob(jobId: string): JobModel | null {
    const activeJob = active.value.find((j) => j.id === jobId)
    if (activeJob) return activeJob
    if (current.value?.id === jobId) return current.value
    return history.value.find((j) => j.id === jobId) ?? null
  }

  function applyJob(target: JobModel, fresh: JobModel): JobModel {
    Object.assign(target, fresh)
    return target
  }

  function reconcileJobs(response: Awaited<ReturnType<typeof api.listJobs>>) {
    const known = new Map<string, JobModel>()
    for (const job of active.value) known.set(job.id, job)
    if (current.value) known.set(current.value.id, current.value)
    for (const job of history.value) known.set(job.id, job)

    const reconcile = (fresh: JobModel): JobModel => {
      const existing = known.get(fresh.id)
      if (existing) return applyJob(existing, fresh)
      known.set(fresh.id, fresh)
      return fresh
    }

    active.value = response.active.map(reconcile)
    current.value = active.value[0] ?? (response.current ? reconcile(response.current) : null)
    history.value = response.history.map(reconcile)
  }

  async function refresh() {
    const sequence = ++refreshSequence
    activeRefreshSequence += 1
    loading.value = true
    error.value = null
    try {
      const response = await api.listJobs()
      if (sequence !== refreshSequence) return
      reconcileJobs(response)
    } catch (err) {
      if (sequence === refreshSequence) {
        error.value = (err as Error).message
      }
    } finally {
      if (sequence === refreshSequence) {
        loading.value = false
      }
    }
  }

  async function refreshActiveJobs() {
    const sequence = ++activeRefreshSequence
    const jobsToRefresh: JobModel[] = []
    for (const job of activeJobs.value) {
      if (isActive(job)) jobsToRefresh.push(job)
    }
    for (const job of history.value) {
      if (isActive(job)) jobsToRefresh.push(job)
    }
    if (!jobsToRefresh.length) return
    const results = await Promise.allSettled(
      jobsToRefresh.map((job) => api.getJob(job.id))
    )
    if (sequence !== activeRefreshSequence) return
    let foundTerminalJob = false
    for (let i = 0; i < results.length; i += 1) {
      const result = results[i]
      if (result.status !== 'fulfilled') continue
      const fresh = result.value
      const slot = findJob(fresh.id)
      if (slot) {
        applyJob(slot, fresh)
      }
      if (TERMINAL_STATUSES.has(fresh.status)) foundTerminalJob = true
    }
    if (foundTerminalJob) await refresh()
  }

  function startPolling() {
    if (pollTimer !== null) return
    pollTimer = window.setInterval(() => {
      void refreshActiveJobs()
    }, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function appendEvent(event: string, data: unknown) {
    const list = events.value
    list.push({ event, data, timestamp: new Date().toISOString() })
    if (list.length > 200) {
      events.value = list.slice(-200)
    }
  }

  function closeStream(jobId?: string | null) {
    if (jobId && activeStreamJobId && jobId !== activeStreamJobId) return
    if (activeStream) {
      activeStream.close()
      activeStream = null
    }
    activeStreamJobId = null
  }

  function follow(jobId: string) {
    if (activeStream && activeStreamJobId === jobId) return
    closeStream()
    activeStreamJobId = jobId
    refresh().then(() => {
      if (activeStreamJobId !== jobId) return
      const job = findJob(jobId)
      if (job) {
        for (const [key, value] of Object.entries(job.progress)) {
          appendEvent('progress', { [key]: value })
        }
      }
      activeStream = openSse(`/api/jobs/${jobId}/events`, {
        onOpen: () => {
          events.value = []
        },
        onEvent: (evt) => {
          try {
            const data = JSON.parse(evt.data)
            appendEvent(evt.event, data)
            if (typeof data === 'object' && data !== null) {
              const d = data as Record<string, unknown>
              const existing = findJob(jobId)
              if (evt.event === 'snapshot' && existing) {
                Object.assign(existing, d)
              }
              const eventStatus = EVENT_STATUSES[evt.event]
              if (eventStatus && existing) {
                existing.status = eventStatus
              }
              if (evt.event === 'log' && existing) {
                const message = typeof d.message === 'string' ? d.message : ''
                if (message) {
                  existing.logs = [...existing.logs, message].slice(-500)
                  existing.progress = { ...existing.progress, message }
                }
              }
              if (typeof d.current === 'number' && typeof d.total === 'number') {
                if (existing) {
                  existing.progress = { ...existing.progress, ...d }
                }
              }
              if (eventStatus && TERMINAL_STATUSES.has(eventStatus)) {
                if (existing) {
                  if (d.result && typeof d.result === 'object') existing.result = d.result as Record<string, unknown>
                  if (d.error && typeof d.error === 'object') existing.error = d.error as JobModel['error']
                }
                void refresh()
                closeStream(jobId)
              }
            }
          } catch (_) {
            // ignore JSON parse errors
          }
        },
        onClose: () => {
          if (activeStreamJobId === jobId) {
            activeStream = null
            activeStreamJobId = null
          }
          refresh()
        }
      }, { token: getAuthToken() })
    })
  }

  async function cancel(jobId: string) {
    error.value = null
    try {
      const fresh = await api.cancelJob(jobId)
      activeRefreshSequence += 1
      const existing = findJob(jobId)
      if (existing) applyJob(existing, fresh)
      await refresh()
    } catch (err) {
      error.value = (err as Error).message
      throw err
    }
  }

  async function forceStop(jobId: string) {
    error.value = null
    try {
      const fresh = await api.forceStopJob(jobId)
      activeRefreshSequence += 1
      const existing = findJob(jobId)
      if (existing) applyJob(existing, fresh)
      await refresh()
    } catch (err) {
      error.value = (err as Error).message
      throw err
    }
  }

  async function remove(jobId: string) {
    await api.deleteJob(jobId)
    await refresh()
  }

  async function clear() {
    await api.clearJobs()
    await refresh()
  }

  return {
    current,
    active,
    activeJobs,
    history,
    events,
    error,
    loading,
    refresh,
    refreshActiveJobs,
    startPolling,
    stopPolling,
    follow,
    cancel,
    forceStop,
    remove,
    clear,
    closeStream,
    findJob
  }
})
