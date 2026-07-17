import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import { api } from '@/api/client'

export function useRules(novel: MaybeRefOrGetter<string>) {
  const rules = ref('')
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const successMessage = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    successMessage.value = null
    try {
      const data = await api.getNovelRules(toValue(novel))
      rules.value = data.rules || ''
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function save() {
    saving.value = true
    error.value = null
    successMessage.value = null
    try {
      await api.saveNovelRules(toValue(novel), rules.value)
      successMessage.value = 'Rules saved successfully.'
      setTimeout(() => {
        if (successMessage.value === 'Rules saved successfully.') successMessage.value = null
      }, 3000)
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      saving.value = false
    }
  }

  return { rules, loading, saving, error, successMessage, load, save }
}
