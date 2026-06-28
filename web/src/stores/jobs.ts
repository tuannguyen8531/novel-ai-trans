import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, getAuthToken } from '@/api/client'
import { openSse, type SseClient } from '@/api/sse'
import type { JobModel } from '@/api/types'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancelling'])
const POLL_INTERVAL_MS = 10_000

export const useJobsStore = defineStore('jobs', () => {
  const current = ref<JobModel | null>(null)
  const history = ref<JobModel[]>([])
  const events = ref<{ event: string, data: unknown, timestamp: string }[]>([])
  const error = ref<string | null>(null)
  const loading = ref(false)
  let activeStream: SseClient | null = null
  let pollTimer: number | null = null

  function isActive(job: JobModel | null): job is JobModel {
    return !!job && ACTIVE_STATUSES.has(job.status)
  }

  function findJob(jobId: string): JobModel | null {
    if (current.value?.id === jobId) return current.value
    return history.value.find((j) => j.id === jobId) ?? null
  }

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      const response = await api.listJobs()
      current.value = response.current
      history.value = response.history
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function refreshActiveJobs() {
    const active: JobModel[] = []
    const currentJob = current.value
    if (isActive(currentJob)) active.push(currentJob)
    for (const job of history.value) {
      if (isActive(job)) active.push(job)
    }
    if (!active.length) return
    const results = await Promise.allSettled(
      active.map((job) => api.getJob(job.id))
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

  function closeStream() {
    if (activeStream) {
      activeStream.close()
      activeStream = null
    }
  }

  function follow(jobId: string) {
    closeStream()
    refresh().then(() => {
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
                closeStream()
              }
            }
          } catch (_) {
            // ignore JSON parse errors
          }
        },
        onClose: () => {
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

  return {
    current,
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
    closeStream,
    findJob
  }
})
