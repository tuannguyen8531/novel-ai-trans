import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'
import type {
  OllamaAccount,
  ProviderCheckSettings,
  ProviderInfo,
  ProviderSettings,
  Settings,
  SettingsPatch,
  TelegramSettings
} from '@/api/types'

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

  async function patch(patch: SettingsPatch) {
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

  async function persist(): Promise<{ path: string; changed_keys: string[] } | null> {
    loading.value = true
    error.value = null
    try {
      return await api.persistSettings()
    } catch (err) {
      error.value = (err as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function persistTelegram(patch: TelegramSettings): Promise<{ path: string; changed_keys: string[] } | null> {
    loading.value = true
    error.value = null
    try {
      const result = await api.persistTelegramSettings(patch)
      settings.value = await api.getSettings()
      return result
    } catch (err) {
      error.value = (err as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function persistProviders(patch: ProviderSettings): Promise<{ path: string; changed_keys: string[] } | null> {
    loading.value = true
    error.value = null
    try {
      const result = await api.persistProviderSettings(patch)
      settings.value = await api.getSettings()
      return result
    } catch (err) {
      error.value = (err as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function listProviders(): Promise<ProviderInfo[]> {
    return (await api.listProviders()).providers
  }

  async function ollamaAccount(): Promise<OllamaAccount> {
    return api.getOllamaAccount()
  }

  async function checkProvider(
    provider: string,
    payload: ProviderCheckSettings
  ): Promise<{ provider: string; ok: boolean; detail: string | null }> {
    return api.checkProvider(provider, payload)
  }

  return {
    settings, error, loading, refresh, patch, persist, persistTelegram, persistProviders,
    listProviders, ollamaAccount, checkProvider
  }
})
