<script setup lang="ts">
import { toRef, watch } from 'vue'
import DetailPanelHeader from '@/components/DetailPanelHeader.vue'
import { useRules } from '@/composables/rules'

const props = defineProps<{
  novel: string
  active: boolean
}>()

const { rules, loading, saving, error, successMessage, load, save } = useRules(toRef(props, 'novel'))

watch(() => props.active, (active) => {
  if (active) void load()
}, { immediate: true })
</script>

<template>
  <div
    v-show="active"
    id="rules-panel"
    class="detail-tab-panel"
    role="tabpanel"
    aria-labelledby="rules-tab"
  >
    <div class="rules-editor">
      <DetailPanelHeader
        title="Novel Translation Rules"
        description="These instructions apply only to this novel. Markdown is supported."
      />
      <textarea
        v-model="rules"
        class="rules-textarea"
        placeholder="e.g.
- Xưng hô 'ta' - 'ngươi' giữa hai nhân vật chính.
- Giữ nguyên tên chiêu thức bằng Hán-Việt."
        :disabled="loading"
      ></textarea>
      <div class="row gap-2 rules-actions">
        <button type="button" :disabled="saving || loading" @click="save">
          {{ saving ? 'Saving...' : 'Save Rules' }}
        </button>
        <button class="secondary" type="button" :disabled="saving || loading" @click="load">
          {{ loading ? 'Reloading...' : 'Reload' }}
        </button>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="successMessage" class="success-message">{{ successMessage }}</div>
    </div>
  </div>
</template>

<style scoped>
.detail-tab-panel {
  padding: 1rem;
}

.rules-editor {
  display: flex;
  flex-direction: column;
}

.rules-textarea {
  width: 100%;
  min-height: 400px;
  padding: 0.75rem;
  color: var(--text-color);
  font-family: monospace;
  resize: vertical;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 4px;
}

.rules-actions {
  margin-top: 0.75rem;
}

.success-message {
  margin-top: 0.6rem;
  color: var(--color-success, #4caf50);
  font-weight: bold;
}

.rules-editor > .error {
  margin-top: 0.6rem;
}
</style>
