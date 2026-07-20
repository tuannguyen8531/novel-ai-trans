<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <header class="detail-panel-header">
    <div class="detail-panel-copy">
      <h3>{{ title }}</h3>
      <p v-if="description" class="muted">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="detail-panel-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.detail-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.detail-panel-copy {
  min-width: 0;
  flex: 1;
}

.detail-panel-copy h3,
.detail-panel-copy p {
  margin: 0;
}

.detail-panel-copy h3 + p {
  margin-top: 0.35rem;
}

.detail-panel-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 0 0 auto;
}
</style>
