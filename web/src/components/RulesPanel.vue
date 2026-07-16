<script setup lang="ts">
import { toRef, watch } from 'vue'
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
      <div class="rules-editor-header">
        <div class="rules-editor-copy">
          <h3>Novel Translation Rules</h3>
          <p class="muted">
            These instructions will be appended to the translation rules for this novel only. You can use Markdown.
          </p>
        </div>
        <button type="button" :disabled="saving || loading" @click="save">
          {{ saving ? 'Saving...' : 'Save Rules' }}
        </button>
      </div>
      <textarea
        v-model="rules"
        class="rules-textarea"
        placeholder="e.g.
- Xưng hô 'ta' - 'ngươi' giữa hai nhân vật chính.
- Giữ nguyên tên chiêu thức bằng Hán-Việt."
        :disabled="loading"
      ></textarea>
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
  gap: 0.6rem;
}

.rules-editor-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
}

.rules-editor-copy {
  min-width: 0;
  flex: 1 1 24rem;
}

.rules-editor-copy h3,
.rules-editor-copy p {
  margin: 0;
}

.rules-editor-copy h3 {
  margin-bottom: 0.35rem;
}

.rules-editor-header button {
  flex: 0 0 auto;
  margin-bottom: 0.1rem;
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

.success-message {
  color: var(--color-success, #4caf50);
  font-weight: bold;
}

@media (max-width: 640px) {
  .rules-editor-header {
    align-items: flex-start;
  }

  .rules-editor-header button {
    margin-bottom: 0;
  }
}
</style>
