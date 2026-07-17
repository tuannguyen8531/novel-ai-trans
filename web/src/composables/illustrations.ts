import { onUnmounted, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { api, getAuthToken } from '@/api/client'

export function useIllustrations(novel: MaybeRefOrGetter<string>, filenames: MaybeRefOrGetter<string[]>) {
  const objectUrls = ref<Map<string, string>>(new Map())
  const loadingImages = ref<Set<string>>(new Set())
  const authenticated = () => Boolean(getAuthToken())

  function src(filename: string): string {
    if (!authenticated()) return api.illustrationUrl(toValue(novel), filename)
    return objectUrls.value.get(filename) ?? ''
  }

  async function load(filename: string): Promise<void> {
    if (objectUrls.value.has(filename) || loadingImages.value.has(filename)) return
    loadingImages.value.add(filename)
    try {
      const token = getAuthToken()
      const response = await fetch(
        api.illustrationUrl(toValue(novel), filename),
        token ? { headers: { Authorization: `Bearer ${token}` } } : {}
      )
      if (!response.ok) return
      objectUrls.value.set(filename, URL.createObjectURL(await response.blob()))
    } finally {
      loadingImages.value.delete(filename)
    }
  }

  watch(
    () => toValue(filenames),
    (values) => {
      if (!authenticated()) return
      for (const filename of values) void load(filename)
    },
    { immediate: true }
  )

  onUnmounted(() => {
    for (const url of objectUrls.value.values()) URL.revokeObjectURL(url)
  })

  return { authenticated, src }
}
