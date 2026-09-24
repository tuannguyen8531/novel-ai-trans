<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Check } from '@lucide/vue'
import { currentLocale, setLocale, type Locale } from '@/i18n'

interface LanguageOption {
  code: Locale
  label: string
}

const languages: LanguageOption[] = [
  { code: 'vi', label: 'Tiếng Việt' },
  { code: 'en', label: 'English' }
]

const isOpen = ref(false)
const containerRef = ref<HTMLElement | null>(null)

function toggleDropdown() {
  isOpen.value = !isOpen.value
}

function selectLanguage(code: Locale) {
  setLocale(code)
  isOpen.value = false
}

function handleClickOutside(event: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && isOpen.value) {
    isOpen.value = false
  }
}

onMounted(() => {
  window.addEventListener('click', handleClickOutside)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('click', handleClickOutside)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div ref="containerRef" class="lang-dropdown-root">
    <!-- Trigger Button: Initially shows ONLY the active flag -->
    <button
      type="button"
      class="lang-flag-btn"
      :class="{ 'is-open': isOpen }"
      :aria-expanded="isOpen"
      :aria-label="$t('interface_language')"
      :title="currentLocale === 'vi' ? 'Tiếng Việt' : 'English'"
      @click="toggleDropdown"
    >
      <!-- Vietnam Flag -->
      <svg
        v-if="currentLocale === 'vi'"
        viewBox="0 0 60 40"
        width="21"
        height="14"
        class="flag-svg"
        aria-hidden="true"
      >
        <rect width="60" height="40" fill="#da251d" />
        <polygon
          points="30.00,8.00 32.69,16.29 41.41,16.29 34.36,21.42 37.05,29.71 30.00,24.58 22.95,29.71 25.64,21.42 18.59,16.29 27.31,16.29"
          fill="#ffeb3b"
        />
      </svg>

      <!-- English (UK) Flag -->
      <svg
        v-else
        viewBox="0 0 60 40"
        width="21"
        height="14"
        class="flag-svg"
        aria-hidden="true"
      >
        <rect width="60" height="40" fill="#012169" />
        <path d="M0 0 L60 40 M60 0 L0 40" stroke="#ffffff" stroke-width="8" />
        <path d="M0 0 L30 20 M60 0 L30 20 M60 40 L30 20 M0 40 L30 20" stroke="#c8102e" stroke-width="3" stroke-linecap="square" />
        <path d="M30 0 v40 M0 20 h60" stroke="#ffffff" stroke-width="12" />
        <path d="M30 0 v40 M0 20 h60" stroke="#c8102e" stroke-width="7" />
      </svg>
    </button>

    <!-- Dropdown Menu -->
    <Transition name="lang-menu">
      <div v-if="isOpen" class="lang-menu">
        <button
          v-for="lang in languages"
          :key="lang.code"
          type="button"
          class="lang-menu-item"
          :class="{ 'is-selected': currentLocale === lang.code }"
          @click="selectLanguage(lang.code)"
        >
          <!-- Option Flag -->
          <svg
            v-if="lang.code === 'vi'"
            viewBox="0 0 60 40"
            width="20"
            height="13.5"
            class="flag-svg"
            aria-hidden="true"
          >
            <rect width="60" height="40" fill="#da251d" />
            <polygon
              points="30.00,8.00 32.69,16.29 41.41,16.29 34.36,21.42 37.05,29.71 30.00,24.58 22.95,29.71 25.64,21.42 18.59,16.29 27.31,16.29"
              fill="#ffeb3b"
            />
          </svg>

          <svg
            v-else
            viewBox="0 0 60 40"
            width="20"
            height="13.5"
            class="flag-svg"
            aria-hidden="true"
          >
            <rect width="60" height="40" fill="#012169" />
            <path d="M0 0 L60 40 M60 0 L0 40" stroke="#ffffff" stroke-width="8" />
            <path d="M0 0 L30 20 M60 0 L30 20 M60 40 L30 20 M0 40 L30 20" stroke="#c8102e" stroke-width="3" stroke-linecap="square" />
            <path d="M30 0 v40 M0 20 h60" stroke="#ffffff" stroke-width="12" />
            <path d="M30 0 v40 M0 20 h60" stroke="#c8102e" stroke-width="7" />
          </svg>

          <span class="lang-name">{{ lang.label }}</span>

          <Check v-if="currentLocale === lang.code" :size="14" class="check-icon" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.lang-dropdown-root {
  position: relative;
  display: inline-flex;
}

/* Trigger Button: Square border frame displaying only the flag */
.lang-flag-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 1.85rem;
  width: 2.25rem;
  padding: 0;
  border-radius: var(--radius-sm);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  outline: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
  flex-shrink: 0;
}

.lang-flag-btn:hover {
  border-color: var(--border-hover);
  background: var(--bg-surface-active);
  transform: scale(1.05);
}

.lang-flag-btn.is-open {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-subtle);
}

:root[data-theme='dark'] .lang-flag-btn {
  background: rgba(15, 23, 42, 0.85);
  border-color: rgba(99, 102, 241, 0.25);
}

:root[data-theme='dark'] .lang-flag-btn:hover {
  border-color: rgba(99, 102, 241, 0.5);
  background: rgba(30, 41, 59, 0.95);
}

:root[data-theme='dark'] .lang-flag-btn.is-open {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-subtle), 0 0 12px var(--accent-glow);
}

.lang-flag-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Crisp Flag Style */
.flag-svg {
  display: block;
  border-radius: 2px;
  overflow: hidden;
  flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15), 0 1px 2px rgba(0, 0, 0, 0.1);
}

/* Floating Dropdown Menu */
.lang-menu {
  position: absolute;
  top: calc(100% + 0.45rem);
  right: 0;
  min-width: 9.5rem;
  padding: 0.35rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-floating);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

:root[data-theme='dark'] .lang-menu {
  background: rgba(18, 22, 32, 0.95);
  border-color: var(--border-base);
  box-shadow: 0 12px 36px -4px rgba(0, 0, 0, 0.6), 0 4px 12px -2px rgba(0, 0, 0, 0.4);
}

/* Menu Item */
.lang-menu-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  width: 100%;
  padding: 0.5rem 0.65rem;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--fg-secondary);
  font-family: var(--font-sans);
  font-size: 0.825rem;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  user-select: none;
  transition: all var(--transition-fast);
}

.lang-menu-item:hover {
  background: var(--bg-surface-active);
  color: var(--fg-primary);
}

.lang-menu-item.is-selected {
  background: var(--accent-subtle);
  color: var(--accent);
  font-weight: 600;
}

.lang-name {
  flex: 1;
  white-space: nowrap;
}

.check-icon {
  color: var(--accent);
  flex-shrink: 0;
}

/* Transition Animations */
.lang-menu-enter-active,
.lang-menu-leave-active {
  transition: opacity 0.16s cubic-bezier(0.16, 1, 0.3, 1), transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}

.lang-menu-enter-from {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}

.lang-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
