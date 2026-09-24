<script setup lang="ts">
import { computed } from 'vue'
import { RefreshCw } from '@lucide/vue'
import { useProviderModels } from '@/composables/models'
import CustomSelect from '@/components/common/CustomSelect.vue'

const props = defineProps<{
  provider: 'ollama' | 'gemini' | 'openrouter'
  modelValue: string
  label?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const { models, loading, loadError, refresh } = useProviderModels(() => props.provider)

const knownModel = computed(() => models.value.includes(props.modelValue))

const modelOptions = computed(() => {
  const placeholder = loading.value
    ? 'Loading models…'
    : models.value.length
      ? '(pick from list)'
      : 'No models available'
  return [
    { value: '', label: placeholder },
    ...models.value.map((m) => ({ value: m, label: m }))
  ]
})

const onSelect = (value: string | number) => {
  const val = String(value)
  // The empty option is a no-op so the user can keep typing freely.
  if (!val) return
  emit('update:modelValue', val)
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
    <div class="model-input-row">
      <CustomSelect
        :model-value="knownModel ? modelValue : ''"
        :options="modelOptions"
        :disabled="loading || !models.length"
        class="model-select"
        @change="onSelect"
      />
      <input
        type="text"
        :value="modelValue"
        :placeholder="knownModel ? 'Selected from list — type to override' : 'Type model id, or pick from the list'"
        class="model-text-input"
        @input="onInput"
      />
      <button
        type="button"
        class="secondary flex items-center gap-1.5 btn-refresh-models"
        :disabled="loading"
        @click="refresh"
      >
        <RefreshCw :size="13" :class="{ 'animate-spin': loading }" />
        <span>{{ refreshLabel }}</span>
      </button>
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
  gap: 0.35rem;
}

.model-input-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.model-select {
  width: 17rem;
  flex-shrink: 0;
}

.model-text-input {
  flex: 1 1 auto;
  min-width: 10rem;
}

.btn-refresh-models {
  flex-shrink: 0;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .model-input-row {
    flex-direction: column;
    align-items: stretch;
  }
  .model-select {
    width: 100%;
  }
}
</style>
