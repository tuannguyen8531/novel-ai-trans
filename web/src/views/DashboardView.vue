<script setup lang="ts">
import { onMounted, onUnmounted, computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Sparkles,
  FolderDown,
  BookOpen,
  Activity,
  AlertTriangle,
  ArrowRight,
  Library
} from '@lucide/vue'
import { useNovelsStore } from '@/composables/novels'
import { useJobsStore } from '@/composables/jobs'
import { useSettingsStore } from '@/composables/settings'
import JobMonitor from '@/components/JobMonitor.vue'
import NovelCard from '@/components/common/NovelCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const novels = useNovelsStore()
const jobs = useJobsStore()
const settings = useSettingsStore()

onMounted(() => {
  void novels.refresh()
  void jobs.refresh()
  void settings.refresh()
  jobs.startPolling()
})

onUnmounted(() => {
  jobs.stopPolling()
})

const defaultTarget = computed(() => settings.settings?.target_language ?? 'vi')

const totalInput = computed(() =>
  novels.novels.reduce((sum, n) => sum + n.total_input_chapters, 0)
)

const totalTranslated = computed(() =>
  novels.novels.reduce(
    (sum, n) => sum + n.targets.reduce((s, t) => s + t.completed, 0),
    0
  )
)

const activeJobs = computed(() => jobs.activeJobs)

// Novels with issues that need attention
const problemNovels = computed(() => {
  return novels.novels.filter((n) => {
    const prog = n.targets.find((t) => t.target === defaultTarget.value)
    return (prog?.failed ?? 0) > 0 || (prog?.warnings ?? 0) > 0
  })
})

// Recent novels to show on the dashboard (up to 4)
const featuredNovels = computed(() => novels.novels.slice(0, 4))
</script>

<template>
  <div class="dashboard-root">
    <!-- Welcome & Quick Studio Actions -->
    <section class="welcome-banner card-panel">
      <div class="welcome-info">
        <div class="welcome-badge">
          <Sparkles :size="14" />
          <span>AI-Powered Novel Translation</span>
        </div>
        <h2 class="welcome-title">Novel Workspace</h2>
        <p class="welcome-desc">
          Translate, refine, and compile web novels and light novels with precision LLM models.
        </p>
      </div>

      <div class="quick-actions">
        <RouterLink to="/translate" class="quick-btn primary">
          <Sparkles :size="16" />
          <span>Translate Studio</span>
        </RouterLink>
        <RouterLink to="/sources" class="quick-btn secondary">
          <FolderDown :size="16" />
          <span>Add Source</span>
        </RouterLink>
        <RouterLink to="/novels" class="quick-btn secondary">
          <BookOpen :size="16" />
          <span>View Library</span>
        </RouterLink>
      </div>
    </section>

    <!-- Key Metrics Strip -->
    <section class="metrics-grid">
      <div class="metric-card">
        <div class="metric-icon-box">
          <Library :size="20" />
        </div>
        <div class="metric-body">
          <span class="metric-value">{{ novels.novels.length }}</span>
          <span class="metric-label">Novels in Library</span>
        </div>
      </div>

      <div class="metric-card">
        <div class="metric-icon-box accent">
          <BookOpen :size="20" />
        </div>
        <div class="metric-body">
          <span class="metric-value">{{ totalTranslated }} <span class="metric-subval">/ {{ totalInput }}</span></span>
          <span class="metric-label">Chapters Translated</span>
        </div>
      </div>

      <div class="metric-card">
        <div class="metric-icon-box" :class="{ 'pulse-active': activeJobs.length > 0 }">
          <Activity :size="20" />
        </div>
        <div class="metric-body">
          <span class="metric-value">{{ activeJobs.length }}</span>
          <span class="metric-label">Active Background Jobs</span>
        </div>
      </div>
    </section>

    <!-- Attention Needed Callout (if any novel has failed or warning chapters) -->
    <section v-if="problemNovels.length" class="attention-card">
      <div class="attention-icon">
        <AlertTriangle :size="20" />
      </div>
      <div class="attention-content">
        <h4 class="attention-title">Translation Attention Required</h4>
        <p class="attention-desc">
          {{ problemNovels.length }} novel{{ problemNovels.length === 1 ? '' : 's' }} have chapters with translation warnings or failures.
        </p>
        <div class="attention-links">
          <RouterLink
            v-for="p in problemNovels"
            :key="p.name"
            :to="{ path: `/novels/${p.name}`, query: { filter: 'issues' } }"
            class="attention-pill"
          >
            <span>{{ p.title || p.name }}</span>
            <ArrowRight :size="12" />
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- Active Jobs Monitor (if jobs are running) -->
    <section v-if="activeJobs.length" class="active-jobs-section card-panel">
      <div class="section-header">
        <div class="header-left">
          <Activity :size="18" class="section-icon" />
          <h3>Active Operations</h3>
        </div>
        <RouterLink to="/jobs" class="view-all-link">
          All Jobs <ArrowRight :size="14" />
        </RouterLink>
      </div>

      <div class="active-jobs-list">
        <div v-for="job in activeJobs" :key="job.id" class="active-job-item">
          <JobMonitor :job="job" :live="false" />
        </div>
      </div>
    </section>

    <!-- Library Highlights / Continue Translating -->
    <section class="novels-section">
      <div class="section-header">
        <div class="header-left">
          <BookOpen :size="18" class="section-icon" />
          <h3>Library Highlights</h3>
        </div>
        <RouterLink v-if="novels.novels.length" to="/novels" class="view-all-link">
          Explore all {{ novels.novels.length }} novels <ArrowRight :size="14" />
        </RouterLink>
      </div>

      <div v-if="novels.novels.length" class="novels-grid">
        <NovelCard
          v-for="novel in featuredNovels"
          :key="novel.name"
          :novel="novel"
          :target-language="defaultTarget"
        />
      </div>

      <EmptyState
        v-else
        :icon="Library"
        title="Your novel library is empty"
        description="Add a web novel by URL crawl or import an existing EPUB book to begin translating."
      >
        <template #action>
          <div class="empty-actions">
            <RouterLink to="/sources">
              <button type="button">
                <FolderDown :size="16" />
                <span>Import or Crawl Novel</span>
              </button>
            </RouterLink>
          </div>
        </template>
      </EmptyState>
    </section>
  </div>
</template>

<style scoped>
.dashboard-root {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

/* Welcome Banner */
.welcome-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 1.75rem 2rem;
  background: linear-gradient(135deg, var(--bg-surface) 0%, var(--bg-surface-elevated) 100%);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-xl);
  flex-wrap: wrap;
}

.welcome-info {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-width: 32rem;
}

.welcome-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.welcome-title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.welcome-desc {
  margin: 0;
  font-size: 0.925rem;
  color: var(--fg-secondary);
  line-height: 1.5;
}

.quick-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.quick-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1.15rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.quick-btn.primary {
  background: var(--accent);
  color: #ffffff;
  box-shadow: 0 4px 14px -2px var(--accent-glow);
}

.quick-btn.primary:hover {
  background: var(--accent-strong);
  transform: translateY(-1px);
}

.quick-btn.secondary {
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--fg-primary);
}

.quick-btn.secondary:hover {
  background: var(--bg-surface-active);
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1rem;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  transition: border-color var(--transition-fast);
}

.metric-card:hover {
  border-color: var(--border-hover);
}

.metric-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  color: var(--fg-secondary);
  flex-shrink: 0;
}

.metric-icon-box.accent {
  background: var(--accent-subtle);
  color: var(--accent);
  border-color: rgba(79, 125, 249, 0.2);
}

.metric-icon-box.pulse-active {
  background: var(--accent-subtle);
  color: var(--accent);
  animation: pulse-ring 2s infinite;
}

.metric-body {
  display: flex;
  flex-direction: column;
}

.metric-value {
  font-size: 1.625rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.metric-subval {
  font-size: 0.95rem;
  font-weight: 400;
  color: var(--fg-muted);
}

.metric-label {
  font-size: 0.8125rem;
  color: var(--fg-secondary);
  margin-top: 0.2rem;
}

/* Attention Needed Card */
.attention-card {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  background: var(--warn-subtle);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: var(--radius-lg);
}

.attention-icon {
  color: var(--warn);
  margin-top: 0.15rem;
  flex-shrink: 0;
}

.attention-content {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
}

.attention-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--warn);
}

.attention-desc {
  margin: 0;
  font-size: 0.875rem;
  color: var(--fg-primary);
}

.attention-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.attention-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.65rem;
  border-radius: var(--radius-pill);
  background: var(--bg-surface);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: var(--fg-primary);
  font-size: 0.8rem;
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.attention-pill:hover {
  background: var(--bg-surface-elevated);
  border-color: var(--warn);
  color: var(--warn);
}

/* Active Jobs Section */
.active-jobs-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.25rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.section-icon {
  color: var(--accent);
}

.section-header h3 {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--fg-primary);
}

.view-all-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--accent);
  text-decoration: none;
  transition: all var(--transition-fast);
}

.view-all-link:hover {
  color: var(--accent-light);
  transform: translateX(2px);
}

.active-jobs-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.active-job-item {
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  padding: 1rem;
  background: var(--bg-surface-elevated);
}

/* Novels Section */
.novels-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.novels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.25rem;
}

.empty-actions {
  display: flex;
  gap: 0.75rem;
}

@keyframes pulse-ring {
  0%, 100% { border-color: rgba(79, 125, 249, 0.2); }
  50% { border-color: rgba(79, 125, 249, 0.6); }
}
</style>
