import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'
import type { Settings } from '@/api/types'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      settings.value = await api.getSettings()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function patch(patch: Partial<Settings>) {
    loading.value = true
    error.value = null
    try {
      settings.value = await api.patchSettings(patch)
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  return { settings, error, loading, refresh, patch }
})
