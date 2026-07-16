import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { api } from '@/api/client'
import type { ArtifactInfo } from '@/api/types'
import type { TargetLanguage } from '@/composables/metadata'

export function useArtifacts(
  novel: MaybeRefOrGetter<string>,
  targetLanguage: MaybeRefOrGetter<TargetLanguage>
) {
  const artifacts = ref<ArtifactInfo[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const packError = ref<string | null>(null)
  const deleteSaving = ref(false)

  const visible = computed(() => artifacts.value.filter(
    (artifact) => artifact.target_language === toValue(targetLanguage)
  ))

  async function load() {
    loading.value = true
    error.value = null
    try {
      artifacts.value = await api.listArtifacts(toValue(novel))
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function download(name: string) {
    error.value = null
    try {
      const blob = await api.downloadArtifact(toValue(novel), name)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = name
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  async function remove(name: string): Promise<boolean> {
    deleteSaving.value = true
    error.value = null
    try {
      await api.deleteArtifact(toValue(novel), name)
      await load()
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    } finally {
      deleteSaving.value = false
    }
  }

  async function startPack(title: string, author: string): Promise<string | null> {
    packError.value = null
    const payload: Record<string, unknown> = {
      novel: toValue(novel),
      target_language: toValue(targetLanguage)
    }
    if (title.trim()) payload.title = title.trim()
    if (author.trim()) payload.author = author.trim()
    try {
      const result = await api.startPack(payload)
      return result.job_id
    } catch (err) {
      packError.value = (err as Error).message
      return null
    }
  }

  return {
    loading,
    error,
    packError,
    deleteSaving,
    visible,
    load,
    download,
    remove,
    startPack
  }
}
