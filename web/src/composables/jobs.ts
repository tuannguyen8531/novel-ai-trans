import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, getAuthToken } from '@/api/client'
import { openSse, type SseClient } from '@/api/sse'
import type { JobModel } from '@/api/types'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancelling'])
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

  function isActive(job: JobModel | null): job is JobModel {
    return !!job && ACTIVE_STATUSES.has(job.status)
  }

  function findJob(jobId: string): JobModel | null {
    const activeJob = active.value.find((j) => j.id === jobId)
    if (activeJob) return activeJob
    if (current.value?.id === jobId) return current.value
    return history.value.find((j) => j.id === jobId) ?? null
  }

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      const response = await api.listJobs()
      active.value = response.active
      current.value = active.value[0] ?? response.current ?? null
      history.value = response.history
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function refreshActiveJobs() {
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
    for (let i = 0; i < results.length; i += 1) {
      const result = results[i]
      if (result.status !== 'fulfilled') continue
      const fresh = result.value
      const slot = findJob(fresh.id)
      if (slot) {
        Object.assign(slot, fresh)
      }
    }
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
              if (['completed', 'failed', 'cancelled'].includes(evt.event)) {
                if (existing) {
                  existing.status = evt.event as JobModel['status']
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
    try {
      await api.cancelJob(jobId)
      await refresh()
    } catch (err) {
      error.value = (err as Error).message
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
    remove,
    clear,
    closeStream,
    findJob
  }
})
