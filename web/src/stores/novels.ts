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

  return { novels, detail, error, loading, refresh, load }
})
