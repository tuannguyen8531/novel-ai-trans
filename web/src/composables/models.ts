import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { api } from '@/api/client'

export function useProviderModels(provider: MaybeRefOrGetter<string>) {
  const models = ref<string[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)

  async function refresh() {
    loading.value = true
    loadError.value = null
    try {
      models.value = (await api.listProviderModels(toValue(provider))).models
    } catch (err) {
      loadError.value = (err as Error).message
      models.value = []
    } finally {
      loading.value = false
    }
  }

  watch(() => toValue(provider), refresh, { immediate: true })
  return { models, loading, loadError, refresh }
}
