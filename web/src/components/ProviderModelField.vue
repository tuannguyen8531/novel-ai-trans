<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{
  provider: 'ollama' | 'gemini' | 'openrouter'
  modelValue: string
  label?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const models = ref<string[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)

async function refresh() {
  loading.value = true
  loadError.value = null
  try {
    const result = await api.listProviderModels(props.provider)
    models.value = result.models
  } catch (err) {
    loadError.value = (err as Error).message
    models.value = []
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
// Refresh when the provider switches (e.g. user changes the default).
watch(() => props.provider, refresh)

const knownModel = computed(() => models.value.includes(props.modelValue))

const onSelect = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  // The empty option is a no-op so the user can keep typing freely.
  if (!value) return
  emit('update:modelValue', value)
}

const onInput = (event: Event) => {
  const value = (event.target as HTMLInputElement).value
  emit('update:modelValue', value)
}

const refreshLabel = computed(() => (loading.value ? 'Refreshing…' : 'Refresh'))
</script>

<template>
  <div class="model-field">
    <label v-if="label">{{ label }}</label>
    <div class="row gap-1" style="align-items: center;">
      <select
        :value="knownModel ? modelValue : ''"
        :disabled="loading || !models.length"
        @change="onSelect"
      >
        <option value="">
          {{ loading ? 'Loading models…' : (models.length ? '(custom / not listed)' : 'No models available') }}
        </option>
        <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
      </select>
      <input
        type="text"
        :value="modelValue"
        :placeholder="knownModel ? 'Selected from list — type to override' : 'Type model id, or pick from the list'"
        @input="onInput"
        style="flex: 1 1 auto;"
      />
      <button
        type="button"
        class="secondary"
        :disabled="loading"
        @click="refresh"
      >{{ refreshLabel }}</button>
    </div>
    <p v-if="loadError" class="error" style="margin-top: 0.25rem; font-size: 0.85rem;">
      {{ loadError }}
    </p>
  </div>
</template>

<style scoped>
.model-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
</style>
