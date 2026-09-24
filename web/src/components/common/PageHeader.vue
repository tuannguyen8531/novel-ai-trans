<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  title: string
  subtitle?: string
  icon?: Component
}>()
</script>

<template>
  <header class="page-header-root">
    <div class="header-main">
      <div v-if="icon" class="header-icon-box">
        <component :is="icon" class="header-icon" />
      </div>
      <div>
        <h1 class="header-title">{{ title }}</h1>
        <p v-if="subtitle" class="header-subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header-root {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}

.header-main {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}

.header-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: var(--radius-lg);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--accent);
  box-shadow: var(--shadow-subtle);
  flex-shrink: 0;
}

.header-icon {
  width: 1.35rem;
  height: 1.35rem;
}

.header-title {
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.header-subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: var(--fg-secondary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
