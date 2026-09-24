<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    status?: string | null
    label?: string | null
    size?: 'sm' | 'md'
    pulse?: boolean
  }>(),
  {
    status: 'normal',
    label: null,
    size: 'md',
    pulse: false
  }
)

const normalizedStatus = computed(() => {
  const s = (props.status || 'normal').toLowerCase()
  if (['completed', 'ok', 'success', 'normal', 'configured', 'safe'].includes(s)) return 'ok'
  if (['warn', 'warning', 'degraded', 'cancelling', 'cancelled', 'ambiguous'].includes(s)) return 'warn'
  if (['danger', 'error', 'failed', 'missing key', 'conflict'].includes(s)) return 'danger'
  if (['running', 'translating', 'active'].includes(s)) return 'running'
  if (['queued', 'pending', 'waiting'].includes(s)) return 'info'
  if (['reviewed'].includes(s)) return 'violet'
  return 'default'
})

const displayLabel = computed(() => {
  if (props.label) return props.label
  const s = props.status || 'normal'
  return s.replace(/_/g, ' ')
})
</script>

<template>
  <span
    class="status-pill"
    :class="[
      `status-${normalizedStatus}`,
      `size-${size}`,
      { 'has-pulse': pulse || normalizedStatus === 'running' }
    ]"
  >
    <span class="status-dot" aria-hidden="true" />
    <span class="status-text">{{ displayLabel }}</span>
  </span>
</template>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  border-radius: var(--radius-pill);
  font-family: var(--font-sans);
  font-weight: 500;
  line-height: 1;
  text-transform: capitalize;
  letter-spacing: 0.01em;
  border: 1px solid transparent;
  white-space: nowrap;
  user-select: none;
  transition: all var(--transition-fast);
}

.size-sm {
  padding: 0.15rem 0.5rem;
  font-size: 0.7rem;
}

.size-md {
  padding: 0.25rem 0.65rem;
  font-size: 0.75rem;
}

.status-dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  flex-shrink: 0;
  background: currentColor;
}

/* Status variants */
.status-ok {
  color: var(--ok);
  background: var(--ok-subtle);
  border-color: rgba(16, 185, 129, 0.25);
}

.status-warn {
  color: var(--warn);
  background: var(--warn-subtle);
  border-color: rgba(245, 158, 11, 0.25);
}

.status-danger {
  color: var(--danger);
  background: var(--danger-subtle);
  border-color: rgba(244, 63, 94, 0.25);
}

.status-info {
  color: var(--info);
  background: var(--info-subtle);
  border-color: rgba(6, 182, 212, 0.25);
}

.status-violet {
  color: var(--violet);
  background: var(--violet-subtle);
  border-color: rgba(139, 92, 246, 0.25);
}

.status-running {
  color: var(--accent);
  background: var(--accent-subtle);
  border-color: rgba(79, 125, 249, 0.3);
}

.status-default {
  color: var(--fg-secondary);
  background: var(--bg-surface-elevated);
  border-color: var(--border-base);
}

/* Pulsing effect for running/active states */
.has-pulse .status-dot {
  animation: status-pulse 1.8s ease-in-out infinite;
}

@keyframes status-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.35);
    opacity: 0.4;
  }
}
</style>
