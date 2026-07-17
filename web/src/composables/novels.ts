import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'
import type { NovelDetail, NovelSummary } from '@/api/types'

export const useNovelsStore = defineStore('novels', () => {
  const novels = ref<NovelSummary[]>([])
  const detail = ref<NovelDetail | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      novels.value = await api.listNovels()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function load(name: string) {
    loading.value = true
    error.value = null
    try {
      detail.value = await api.getNovel(name)
    } catch (err) {
      error.value = (err as Error).message
      detail.value = null
    } finally {
      loading.value = false
    }
  }

  async function remove(name: string) {
    await api.deleteNovel(name)
    novels.value = novels.value.filter((novel) => novel.name !== name)
    if (detail.value?.name === name) {
      detail.value = null
    }
  }

  async function create(payload: { name: string; title?: string; author?: string; source_language?: string; illustration_url?: string }) {
    await api.createNovel(payload)
    await refresh()
  }

  async function progress(name: string, target: string): Promise<{ completed: number[]; failed: number[] }> {
    return api.getTranslationProgress(name, target)
  }

  return { novels, detail, error, loading, refresh, load, remove, create, progress }
})
