<script setup lang="ts">
defineProps<{
  pendingCount: number
  loading: boolean
}>()

const emit = defineEmits<{
  preview: []
  dismiss: []
}>()
</script>

<template>
  <div v-if="pendingCount" class="pending-banner">
    <div class="pending-banner-text">
      <span>
        ⚠️ You have <strong>{{ pendingCount }}</strong> pending glossary changes waiting to be
        applied to translated chapters.
      </span>
    </div>
    <div class="pending-banner-actions">
      <button type="button" :disabled="loading" @click="emit('preview')">Preview & Apply</button>
      <button type="button" class="secondary" :disabled="loading" @click="emit('dismiss')">
        Dismiss
      </button>
    </div>
  </div>
</template>

<style scoped>
.pending-banner {
  background: rgba(240, 184, 106, 0.1);
  border: 1px solid var(--warn);
  border-radius: var(--radius);
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}

.pending-banner-text {
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pending-banner-actions {
  display: flex;
  gap: 0.5rem;
}
</style>
