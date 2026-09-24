<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    height?: string
  }>(),
  {
    height: '10rem'
  }
)
</script>

<template>
  <div class="loading-state" :style="{ minHeight: height }">
    <div class="spinner" aria-hidden="true" />
    <span class="loading-label">{{ label || $t('loading') }}</span>
  </div>
</template>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  width: 100%;
  color: var(--fg-muted);
}

.spinner {
  width: 1.75rem;
  height: 1.75rem;
  border: 2px solid var(--border-base);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--fg-secondary);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
