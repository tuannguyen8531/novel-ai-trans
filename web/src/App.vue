<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterView, RouterLink, useRoute } from 'vue-router'
import { setAuthToken } from '@/api/client'

const route = useRoute()
const theme = ref<'dark' | 'light'>('dark')
const apiKey = ref('')
const authVersion = ref(0)

onMounted(() => {
  const stored = localStorage.getItem('theme') as 'dark' | 'light' | null
  if (stored === 'light') {
    theme.value = 'light'
  }
  document.documentElement.dataset.theme = theme.value
})

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('theme', theme.value)
}

function applyApiKey() {
  setAuthToken(apiKey.value.trim() || null)
  authVersion.value += 1
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">N·A·T</span>
        <span class="brand-name">novel-ai-trans</span>
      </div>
      <nav class="nav">
        <RouterLink to="/">Dashboard</RouterLink>
        <RouterLink to="/novels">Novels</RouterLink>
        <RouterLink to="/crawl">Crawl</RouterLink>
        <RouterLink to="/import">Import</RouterLink>
        <RouterLink to="/translate">Translate</RouterLink>
        <RouterLink to="/jobs">Jobs</RouterLink>
        <RouterLink to="/settings">Settings</RouterLink>
      </nav>
      <div class="sidebar-footer">
        <label class="api-key-label" for="api-key">API key (remote mode)</label>
        <input id="api-key" v-model="apiKey" type="password" autocomplete="off" @keyup.enter="applyApiKey" />
        <button class="secondary" type="button" @click="applyApiKey">Apply API key</button>
        <button class="secondary" type="button" @click="toggleTheme">
          {{ theme === 'dark' ? '☾ Dark' : '☀ Light' }}
        </button>
      </div>
    </aside>
    <main class="content">
      <header class="page-header">
        <h1 class="page-title">{{ String(route.name ?? '') }}</h1>
      </header>
      <RouterView :key="`${route.fullPath}:${authVersion}`" />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}

.sidebar {
  background: var(--bg-elev);
  border-right: 1px solid var(--border);
  padding: 1rem 0.75rem;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 1rem;
}

.brand-mark {
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.18em;
  color: var(--accent);
}

.brand-name {
  font-weight: 600;
  font-size: 0.95rem;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.nav a {
  padding: 0.45rem 0.7rem;
  border-radius: var(--radius);
  color: var(--fg);
}

.nav a.router-link-active,
.nav a.router-link-exact-active {
  background: var(--bg-elev-2);
  color: var(--accent);
}

.sidebar-footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.api-key-label {
  color: var(--fg-dim);
  font-size: 0.75rem;
}

.content {
  padding: 1.25rem 1.5rem;
  max-width: 1200px;
}

.page-header {
  margin-bottom: 1rem;
}

.page-title {
  font-size: 1.5rem;
  margin: 0;
  text-transform: capitalize;
}
</style>
