<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  title: string
  description?: string
  icon?: Component
}>()
</script>

<template>
  <div class="empty-state">
    <div v-if="icon" class="empty-icon-wrap">
      <component :is="icon" class="empty-icon" />
    </div>
    <h3 class="empty-title">{{ title }}</h3>
    <p v-if="description" class="empty-description">{{ description }}</p>
    <div v-if="$slots.action" class="empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 3rem 1.5rem;
  border-radius: var(--radius-lg);
  border: 1px dashed var(--border-base);
  background: var(--bg-surface-subtle);
}

.empty-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3.5rem;
  height: 3.5rem;
  margin-bottom: 1rem;
  border-radius: 50%;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--accent);
}

.empty-icon {
  width: 1.75rem;
  height: 1.75rem;
}

.empty-title {
  margin: 0 0 0.4rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--fg-primary);
}

.empty-description {
  margin: 0;
  max-width: 26rem;
  font-size: 0.875rem;
  color: var(--fg-secondary);
  line-height: 1.5;
}

.empty-action {
  margin-top: 1.25rem;
}
</style>
