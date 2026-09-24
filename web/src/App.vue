<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterView, RouterLink, useRoute } from 'vue-router'
import {
  LayoutDashboard,
  BookOpen,
  Sparkles,
  FolderDown,
  Activity,
  Settings,
  Sun,
  Moon,
  Menu,
  X,
  KeyRound,
  ChevronRight,
  Loader2
} from '@lucide/vue'
import { setAuthToken, getAuthToken } from '@/api/client'
import { pageTitle } from '@/router'
import { useJobsStore } from '@/composables/jobs'
import { useBodyScrollLock } from '@/composables/scrolllock'

const route = useRoute()
const jobs = useJobsStore()

const theme = ref<'dark' | 'light'>('dark')
const apiKey = ref('')
const authVersion = ref(0)
const mobileMenuOpen = ref(false)
const showApiKeyModal = ref(false)

useBodyScrollLock(() => showApiKeyModal.value)

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && showApiKeyModal.value) {
    showApiKeyModal.value = false
  }
}

const pageHeading = computed(() => pageTitle(route))
const activeJobsCount = computed(() => jobs.activeJobs.length)
const runningJob = computed(() => jobs.activeJobs[0] ?? null)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  const storedTheme = localStorage.getItem('theme') as 'dark' | 'light' | null
  if (storedTheme === 'light') {
    theme.value = 'light'
  }
  document.documentElement.dataset.theme = theme.value

  const token = getAuthToken()
  if (token) {
    apiKey.value = token
  }

  // Start polling jobs to keep sidebar badge updated
  jobs.startPolling()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  jobs.stopPolling()
})

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('theme', theme.value)
}

function applyApiKey() {
  const cleaned = apiKey.value.trim()
  setAuthToken(cleaned || null)
  authVersion.value += 1
  showApiKeyModal.value = false
}

function clearApiKey() {
  apiKey.value = ''
  setAuthToken(null)
  authVersion.value += 1
  showApiKeyModal.value = false
}

function closeMobileMenu() {
  mobileMenuOpen.value = false
}
</script>

<template>
  <div class="app-shell">
    <!-- Mobile Backdrop -->
    <div
      v-if="mobileMenuOpen"
      class="mobile-backdrop"
      @click="closeMobileMenu"
    />

    <!-- Sidebar Navigation -->
    <aside class="app-sidebar" :class="{ 'is-mobile-open': mobileMenuOpen }">
      <!-- Workspace Brand -->
      <div class="brand-container">
        <RouterLink to="/" class="brand-link" @click="closeMobileMenu">
          <div class="brand-logo-frame">
            <img class="brand-logo-img" src="/icon.png" alt="Logo" width="36" height="36" />
          </div>
          <div class="brand-text">
            <span class="brand-title">NOVEL TRANS</span>
            <span class="brand-subtitle">AI Translation Studio</span>
          </div>
        </RouterLink>

        <button
          type="button"
          class="btn-icon mobile-close-btn"
          aria-label="Close menu"
          @click="closeMobileMenu"
        >
          <X :size="18" />
        </button>
      </div>

      <!-- Navigation Links -->
      <nav class="nav-menu" aria-label="Main Navigation">
        <RouterLink
          to="/"
          class="nav-item"
          :class="{ active: route.name === 'dashboard' }"
          @click="closeMobileMenu"
        >
          <LayoutDashboard :size="18" class="nav-icon" />
          <span class="nav-text">Dashboard</span>
        </RouterLink>

        <RouterLink
          to="/novels"
          class="nav-item"
          :class="{ active: route.name === 'novels' || route.name === 'novel-detail' || route.name === 'chapter-reader' }"
          @click="closeMobileMenu"
        >
          <BookOpen :size="18" class="nav-icon" />
          <span class="nav-text">Novels</span>
        </RouterLink>

        <RouterLink
          to="/translate"
          class="nav-item"
          :class="{ active: route.name === 'translate' }"
          @click="closeMobileMenu"
        >
          <Sparkles :size="18" class="nav-icon" />
          <span class="nav-text">Translate</span>
        </RouterLink>

        <RouterLink
          to="/sources"
          class="nav-item"
          :class="{ active: route.name === 'sources' }"
          @click="closeMobileMenu"
        >
          <FolderDown :size="18" class="nav-icon" />
          <span class="nav-text">Sources</span>
        </RouterLink>

        <RouterLink
          to="/jobs"
          class="nav-item"
          :class="{ active: route.name === 'jobs' }"
          @click="closeMobileMenu"
        >
          <Activity :size="18" class="nav-icon" />
          <span class="nav-text">Jobs</span>
          <span v-if="activeJobsCount > 0" class="nav-badge pulse">
            {{ activeJobsCount }}
          </span>
        </RouterLink>

        <RouterLink
          to="/settings"
          class="nav-item"
          :class="{ active: route.name === 'settings' }"
          @click="closeMobileMenu"
        >
          <Settings :size="18" class="nav-icon" />
          <span class="nav-text">Settings</span>
        </RouterLink>
      </nav>

      <!-- Sidebar Footer Controls -->
      <div class="sidebar-footer">
        <div class="footer-actions">
          <button
            type="button"
            class="footer-btn"
            title="Configure remote API Key"
            @click="showApiKeyModal = true"
          >
            <KeyRound :size="16" />
            <span>{{ apiKey ? 'API Key Set' : 'Remote Key' }}</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- Main Workspace Area -->
    <div class="app-main">
      <!-- Top Bar -->
      <header class="top-bar">
        <div class="top-bar-left">
          <button
            type="button"
            class="mobile-menu-toggle"
            aria-label="Toggle navigation"
            @click="mobileMenuOpen = !mobileMenuOpen"
          >
            <Menu :size="20" />
          </button>

          <!-- Breadcrumbs -->
          <nav class="breadcrumb-nav" aria-label="Breadcrumb">
            <RouterLink to="/" class="breadcrumb-link">Workspace</RouterLink>
            <ChevronRight :size="14" class="breadcrumb-separator" />
            <span class="breadcrumb-current">{{ pageHeading }}</span>
            <template v-if="route.params.name">
              <ChevronRight :size="14" class="breadcrumb-separator" />
              <RouterLink
                v-if="route.name === 'chapter-reader'"
                :to="`/novels/${route.params.name}`"
                class="breadcrumb-link"
              >
                {{ route.params.name }}
              </RouterLink>
              <span v-else class="breadcrumb-current">{{ route.params.name }}</span>
            </template>
            <template v-if="route.params.chapter">
              <ChevronRight :size="14" class="breadcrumb-separator" />
              <span class="breadcrumb-current">Ch. {{ route.params.chapter }}</span>
            </template>
          </nav>
        </div>

        <div class="top-bar-right">
          <!-- Active Job Notification -->
          <RouterLink
            v-if="runningJob"
            to="/jobs"
            class="active-job-indicator"
            title="Active Job in progress"
          >
            <Loader2 :size="14" class="spinning-icon" />
            <span class="active-job-text">
              {{ runningJob.kind }}
              <template v-if="runningJob.novel">({{ runningJob.novel }})</template>
            </span>
          </RouterLink>

          <!-- Smooth Theme Switch -->
          <button
            type="button"
            role="switch"
            class="theme-switch"
            :class="{ 'is-dark': theme === 'dark' }"
            :aria-checked="theme === 'dark'"
            :title="theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'"
            @click="toggleTheme"
          >
            <span class="theme-switch-track">
              <span class="track-icon sun-icon" aria-hidden="true">
                <Sun :size="12" />
              </span>
              <span class="track-icon moon-icon" aria-hidden="true">
                <Moon :size="12" />
              </span>
              <span class="theme-switch-thumb">
                <Moon v-if="theme === 'dark'" :size="12" class="thumb-icon icon-moon" />
                <Sun v-else :size="12" class="thumb-icon icon-sun" />
              </span>
            </span>
          </button>
        </div>
      </header>

      <!-- View Content -->
      <main class="workspace-content">
        <RouterView :key="`${route.fullPath}:${authVersion}`" />
      </main>
    </div>

    <!-- API Key Modal Dialog -->
    <div
      v-if="showApiKeyModal"
      class="modal-overlay"
      @click.self="showApiKeyModal = false"
    >
      <div class="modal-card">
        <header class="modal-header">
          <h3>Remote Server Authentication</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            @click="showApiKeyModal = false"
          >
            <X :size="18" />
          </button>
        </header>
        <div class="modal-body flex-col gap-3">
          <p class="muted" style="margin: 0;">
            Provide an API authentication key when connecting to a remote or protected novel-ai-trans server instance.
          </p>
          <div>
            <label for="modal-api-key">API Key (Bearer token)</label>
            <input
              id="modal-api-key"
              v-model="apiKey"
              type="password"
              placeholder="Paste secret token..."
              autocomplete="off"
              @keyup.enter="applyApiKey"
            />
          </div>
        </div>
        <footer class="modal-footer">
          <button
            v-if="apiKey"
            type="button"
            class="secondary"
            @click="clearApiKey"
          >
            Clear Key
          </button>
          <button
            type="button"
            class="secondary"
            @click="showApiKeyModal = false"
          >
            Cancel
          </button>
          <button type="button" @click="applyApiKey">
            Save Key
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg-base);
  color: var(--fg-primary);
}

/* Sidebar */
.app-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  width: 250px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-base);
  box-sizing: border-box;
  padding: 1.25rem 0.875rem 1rem;
  z-index: 100;
  transition: transform var(--transition-normal);
}

/* Brand */
.brand-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.75rem;
  padding: 0 0.5rem;
}

.brand-link {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  text-decoration: none;
  color: inherit;
}

.brand-logo-frame {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  box-shadow: var(--shadow-subtle);
  overflow: hidden;
  flex-shrink: 0;
}

.brand-logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  font-family: var(--font-sans);
  font-weight: 700;
  font-size: 0.95rem;
  letter-spacing: 0.04em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.brand-subtitle {
  font-size: 0.725rem;
  color: var(--accent);
  letter-spacing: 0.02em;
  font-weight: 500;
}

.mobile-close-btn {
  display: none;
}

/* Nav Menu */
.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius-md);
  color: var(--fg-secondary);
  font-size: 0.9rem;
  font-weight: 500;
  text-decoration: none;
  border: 1px solid transparent;
  transition: all var(--transition-fast);
}

.nav-icon {
  color: var(--fg-muted);
  flex-shrink: 0;
  transition: color var(--transition-fast);
}

.nav-text {
  flex: 1;
}

.nav-item:hover {
  background: var(--bg-surface-elevated);
  color: var(--fg-primary);
  text-decoration: none;
}

.nav-item:hover .nav-icon {
  color: var(--fg-primary);
}

.nav-item.active {
  background: var(--accent-subtle);
  color: var(--accent);
  border-color: rgba(79, 125, 249, 0.2);
  font-weight: 600;
}

.nav-item.active .nav-icon {
  color: var(--accent);
}

.nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.35rem;
  border-radius: var(--radius-pill);
  font-size: 0.75rem;
  font-weight: 700;
  background: var(--accent);
  color: #ffffff;
}

.nav-badge.pulse {
  box-shadow: 0 0 10px var(--accent-glow);
  animation: pulse 1.6s ease-in-out infinite;
}

/* Sidebar Footer */
.sidebar-footer {
  margin-top: auto;
  padding-top: 1rem;
  border-top: 1px solid var(--border-base);
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.footer-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--fg-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  flex: 1;
  justify-content: center;
  transition: all var(--transition-fast);
}

.footer-btn:hover {
  background: var(--bg-surface-active);
  color: var(--fg-primary);
  border-color: var(--border-hover);
  transform: none;
}

/* App Main */
.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg-base);
}

/* Top Bar */
.top-bar {
  position: sticky;
  top: 0;
  height: 3.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.75rem;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-base);
  z-index: 50;
  backdrop-filter: blur(8px);
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.mobile-menu-toggle {
  display: none;
  background: transparent;
  border: none;
  padding: 0.25rem;
  color: var(--fg-secondary);
  cursor: pointer;
}

.breadcrumb-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.breadcrumb-link {
  color: var(--fg-secondary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.breadcrumb-link:hover {
  color: var(--fg-primary);
  text-decoration: underline;
}

.breadcrumb-separator {
  color: var(--fg-muted);
}

.breadcrumb-current {
  color: var(--fg-primary);
  font-weight: 600;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.active-job-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius-pill);
  background: var(--accent-subtle);
  border: 1px solid rgba(79, 125, 249, 0.3);
  color: var(--accent);
  font-size: 0.8rem;
  font-weight: 600;
  text-decoration: none;
  animation: pulse-border 2s infinite;
}

.spinning-icon {
  animation: spin 1.2s linear infinite;
}

/* Smooth Theme Switch */
.theme-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  outline: none;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}

.theme-switch:focus-visible .theme-switch-track {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.theme-switch-track {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 3.35rem;
  height: 1.85rem;
  padding: 0 0.35rem;
  border-radius: var(--radius-pill);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.15);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-switch:hover .theme-switch-track {
  border-color: var(--border-hover);
}

.theme-switch.is-dark .theme-switch-track {
  background: rgba(15, 23, 42, 0.85);
  border-color: rgba(99, 102, 241, 0.35);
}

.track-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  pointer-events: none;
  transition: opacity 0.25s ease;
}

.sun-icon {
  color: #f59e0b;
  opacity: 0.85;
}

.moon-icon {
  color: #818cf8;
  opacity: 0.85;
}

.theme-switch.is-dark .sun-icon {
  opacity: 0.35;
}

.theme-switch:not(.is-dark) .moon-icon {
  opacity: 0.35;
}

.theme-switch-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.45rem;
  height: 1.45rem;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15), 0 1px 2px rgba(0, 0, 0, 0.1);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), background-color 0.3s ease, box-shadow 0.3s ease;
  z-index: 2;
}

.theme-switch.is-dark .theme-switch-thumb {
  transform: translateX(1.5rem);
  background: #1e293b;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35), 0 1px 3px rgba(0, 0, 0, 0.2);
}

.thumb-icon {
  transition: all 0.2s ease;
}

.thumb-icon.icon-sun {
  color: #d97706;
}

.thumb-icon.icon-moon {
  color: #a5b4fc;
}

/* Workspace Content Area */
.workspace-content {
  flex: 1;
  padding: 1.75rem 2rem;
  width: 100%;
  max-width: 1560px;
  margin: 0 auto;
  box-sizing: border-box;
}

/* Mobile responsive styles */
@media (max-width: 900px) {
  .app-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    transform: translateX(-100%);
    box-shadow: var(--shadow-floating);
  }

  .app-sidebar.is-mobile-open {
    transform: translateX(0);
  }

  .mobile-close-btn {
    display: flex;
  }

  .mobile-menu-toggle {
    display: flex;
  }

  .mobile-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    z-index: 90;
  }

  .workspace-content {
    padding: 1.25rem 1rem;
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

@keyframes pulse-border {
  0%, 100% { border-color: rgba(79, 125, 249, 0.3); }
  50% { border-color: rgba(79, 125, 249, 0.7); }
}
</style>
