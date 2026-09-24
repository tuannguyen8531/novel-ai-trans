<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ChevronDown, Check } from '@lucide/vue'

export interface SelectOption {
  value: string | number
  label: string
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  modelValue: string | number
  options: (SelectOption | string | number)[]
  placeholder?: string
  disabled?: boolean
}>(), {
  placeholder: 'Select an option…',
  disabled: false
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
  'change': [value: string | number]
}>()

const isOpen = ref(false)
const selectRef = ref<HTMLElement | null>(null)

const normalizedOptions = computed<SelectOption[]>(() => {
  return props.options.map((opt) => {
    if (typeof opt === 'object' && opt !== null) return opt
    return { value: opt, label: String(opt) }
  })
})

const selectedOption = computed(() => {
  return normalizedOptions.value.find((opt) => opt.value === props.modelValue)
})

function toggleDropdown() {
  if (props.disabled) return
  isOpen.value = !isOpen.value
}

function selectOption(option: SelectOption) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  emit('change', option.value)
  isOpen.value = false
}

function handleClickOutside(event: MouseEvent) {
  if (selectRef.value && !selectRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  if (event.key === 'Escape') {
    isOpen.value = false
  } else if (event.key === 'Enter' || event.key === ' ') {
    if (!isOpen.value) {
      event.preventDefault()
      isOpen.value = true
    }
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!isOpen.value) {
      isOpen.value = true
    } else {
      const currentIndex = normalizedOptions.value.findIndex((o) => o.value === props.modelValue)
      const nextIndex = Math.min(normalizedOptions.value.length - 1, currentIndex + 1)
      const nextOption = normalizedOptions.value[nextIndex]
      if (nextOption && !nextOption.disabled) {
        emit('update:modelValue', nextOption.value)
        emit('change', nextOption.value)
      }
    }
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (isOpen.value) {
      const currentIndex = normalizedOptions.value.findIndex((o) => o.value === props.modelValue)
      const prevIndex = Math.max(0, currentIndex - 1)
      const prevOption = normalizedOptions.value[prevIndex]
      if (prevOption && !prevOption.disabled) {
        emit('update:modelValue', prevOption.value)
        emit('change', prevOption.value)
      }
    }
  }
}

onMounted(() => {
  window.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  window.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div
    ref="selectRef"
    class="custom-select"
    :class="{ 'is-open': isOpen, 'is-disabled': disabled }"
    @keydown="handleKeydown"
  >
    <button
      type="button"
      class="custom-select-trigger"
      :disabled="disabled"
      aria-haspopup="listbox"
      :aria-expanded="isOpen"
      @click.stop="toggleDropdown"
    >
      <span v-if="selectedOption" class="selected-label">
        {{ selectedOption.label }}
      </span>
      <span v-else class="placeholder-label">
        {{ placeholder }}
      </span>

      <ChevronDown :size="16" class="chevron-icon" :class="{ 'is-flipped': isOpen }" />
    </button>

    <Transition name="select-dropdown">
      <div v-if="isOpen" class="custom-select-dropdown" role="listbox">
        <ul class="custom-select-options">
          <li
            v-for="option in normalizedOptions"
            :key="String(option.value)"
            class="custom-select-option"
            :class="{
              'is-selected': option.value === modelValue,
              'is-disabled': option.disabled
            }"
            role="option"
            :aria-selected="option.value === modelValue"
            @click.stop="selectOption(option)"
          >
            <span class="option-label">{{ option.label }}</span>
            <Check v-if="option.value === modelValue" :size="14" class="check-icon" />
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.custom-select {
  position: relative;
  width: 100%;
}

.custom-select-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.55rem 0.85rem;
  background: var(--bg-surface);
  color: var(--fg-primary);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  font-family: var(--font-sans);
  font-size: 0.875rem;
  font-weight: 400;
  text-align: left;
  cursor: pointer;
  box-shadow: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast), background var(--transition-fast);
}

.custom-select-trigger:hover:not(:disabled) {
  border-color: var(--border-hover);
  background: var(--bg-surface);
  transform: none;
  box-shadow: none;
}

.custom-select.is-open .custom-select-trigger {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-subtle);
  background: var(--bg-surface);
}

.custom-select-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  background: var(--bg-surface-elevated);
}

.selected-label {
  color: var(--fg-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.placeholder-label {
  color: var(--fg-muted);
}

.chevron-icon {
  color: var(--fg-muted);
  flex-shrink: 0;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), color var(--transition-fast);
}

.custom-select-trigger:hover .chevron-icon {
  color: var(--fg-primary);
}

.chevron-icon.is-flipped {
  transform: rotate(180deg);
  color: var(--accent);
}

/* Custom Dropdown Frame (Khung option) */
.custom-select-dropdown {
  position: absolute;
  top: calc(100% + 0.35rem);
  left: 0;
  right: 0;
  z-index: 250;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-floating);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 0.35rem;
  max-height: 18rem;
  overflow-y: auto;
}

.custom-select-options {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.custom-select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  color: var(--fg-primary);
  font-size: 0.85rem;
  font-weight: 450;
  cursor: pointer;
  user-select: none;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.custom-select-option:hover:not(.is-disabled) {
  background: var(--bg-surface-active);
  color: var(--fg-primary);
}

.custom-select-option.is-selected {
  background: var(--accent-subtle);
  color: var(--accent-light);
  font-weight: 600;
}

.custom-select-option.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.option-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.check-icon {
  color: var(--accent);
  flex-shrink: 0;
}

/* Dropdown Animation */
.select-dropdown-enter-active,
.select-dropdown-leave-active {
  transition: opacity 0.16s cubic-bezier(0.16, 1, 0.3, 1), transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}

.select-dropdown-enter-from {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}

.select-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
